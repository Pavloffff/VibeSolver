import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Import, IndexRun, ProjectIndex, SourceSnapshot
from app.domain.repositories.indexing import IndexRunStatus


class IndexingSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_completed_import_snapshot(self, source_id: int) -> int | None:
        import_id = await self._session.scalar(
            select(Import.id)
            .where(Import.source_id == source_id, Import.status == "done")
            .order_by(Import.id.desc())
            .limit(1)
        )
        if import_id is None:
            return None
        result = await self._session.scalar(
            select(SourceSnapshot.id).where(SourceSnapshot.import_id == import_id)
        )
        if result is not None:
            return int(result)
        imported = await self._session.execute(
            text(
                "SELECT branch, path, COALESCE(size_bytes, 0) AS size_bytes, "
                "storage_key, content_hash FROM imported_files "
                "WHERE source_id = :source_id ORDER BY branch, path"
            ),
            {"source_id": source_id},
        )
        files = [dict(row._mapping) for row in imported.all()]
        if not files:
            return None
        stable_files = [
            {"branch": row["branch"], "path": row["path"], "content_hash": row["content_hash"]}
            for row in files
        ]
        content_hash = hashlib.sha256(
            json.dumps(stable_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        inserted = await self._session.execute(
            text(
                "INSERT INTO source_snapshots "
                "(source_id, import_id, content_hash, source_revision) "
                "VALUES (:source_id, :import_id, :content_hash, CAST(:source_revision AS jsonb)) "
                "ON CONFLICT (import_id) DO NOTHING RETURNING id"
            ),
            {
                "source_id": source_id,
                "import_id": import_id,
                "content_hash": content_hash,
                "source_revision": json.dumps({"scope": "code", "legacy_import": True}),
            },
        )
        snapshot_id = inserted.scalar_one_or_none()
        if snapshot_id is None:
            snapshot_id = await self._session.scalar(
                select(SourceSnapshot.id).where(SourceSnapshot.import_id == import_id)
            )
            return int(snapshot_id) if snapshot_id is not None else None
        await self._session.execute(
            text(
                "INSERT INTO source_snapshot_files "
                "(snapshot_id, branch, path, size_bytes, storage_key, content_hash, metadata_json) "
                "VALUES (:snapshot_id, :branch, :path, :size_bytes, :storage_key, "
                ":content_hash, '{}'::jsonb)"
            ),
            [{"snapshot_id": snapshot_id, **file} for file in files],
        )
        await self._session.commit()
        return int(snapshot_id)

    async def queue_run(
        self,
        source_id: int,
        index_type: str,
        snapshot_id: int,
        embedding_model_id: int,
        parser_version: str,
        chunker_version: str,
    ) -> int:
        await self._session.execute(
            text(
                "INSERT INTO project_indexes (source_id, index_type, status) "
                "VALUES (:source_id, :index_type, 'not_started') "
                "ON CONFLICT (source_id, index_type) DO NOTHING"
            ),
            {"source_id": source_id, "index_type": index_type},
        )
        project_index = await self._session.scalar(
            select(ProjectIndex)
            .where(ProjectIndex.source_id == source_id, ProjectIndex.index_type == index_type)
            .with_for_update()
        )
        if project_index is None:
            raise RuntimeError("could not create project index state")
        if project_index.status in {"queued", "running"}:
            raise ValueError("an indexing job for this type is already running")
        run = IndexRun(
            project_index_id=project_index.id,
            snapshot_id=snapshot_id,
            status="queued",
            progress=0,
            parser_version=parser_version,
            chunker_version=chunker_version,
            embedding_model_id=embedding_model_id,
        )
        self._session.add(run)
        await self._session.flush()
        project_index.status = "queued"
        await self._session.commit()
        return run.id

    async def statuses(self, source_id: int) -> list[IndexRunStatus]:
        rows = await self._session.execute(
            text(
                "SELECT index_state.index_type, index_state.status, "
                "COALESCE(run.progress, 0) AS progress, run.id AS run_id, "
                "run.snapshot_id, COALESCE(run.files_total, 0) AS files_total, "
                "COALESCE(run.chunks_total, 0) AS chunks_total, run.error, index_state.updated_at, "
                "run.parser_version, run.chunker_version, run.embedding_model_id "
                "FROM project_indexes AS index_state "
                "LEFT JOIN index_runs AS run ON run.id = ("
                "SELECT latest.id FROM index_runs AS latest "
                "WHERE latest.project_index_id = index_state.id "
                "ORDER BY latest.id DESC LIMIT 1) "
                "WHERE index_state.source_id = :source_id ORDER BY index_state.index_type"
            ),
            {"source_id": source_id},
        )
        return [
            IndexRunStatus(
                index_type=str(row.index_type),
                status=str(row.status),
                progress=int(row.progress),
                run_id=int(row.run_id) if row.run_id is not None else None,
                snapshot_id=int(row.snapshot_id) if row.snapshot_id is not None else None,
                files_total=int(row.files_total),
                chunks_total=int(row.chunks_total),
                error=str(row.error) if row.error is not None else None,
                updated_at=row.updated_at,
                parser_version=(str(row.parser_version) if row.parser_version else None),
                chunker_version=(str(row.chunker_version) if row.chunker_version else None),
                embedding_model_id=(
                    int(row.embedding_model_id) if row.embedding_model_id is not None else None
                ),
            )
            for row in rows.all()
        ]

    async def fail_run(self, run_id: int, error: str) -> None:
        run = await self._session.get(IndexRun, run_id)
        if run is None:
            return
        run.status = "failed"
        run.error = error[:1000]
        index_state = await self._session.get(ProjectIndex, run.project_index_id)
        if index_state is not None:
            index_state.status = "failed"
        await self._session.commit()

    async def mark_stale(self, source_id: int, index_types: list[str]) -> None:
        if not index_types:
            return
        await self._session.execute(
            text(
                "UPDATE project_indexes SET status = 'stale', updated_at = now() "
                "WHERE source_id = :source_id AND index_type = ANY(:index_types) "
                "AND status <> 'not_started'"
            ),
            {"source_id": source_id, "index_types": index_types},
        )
        await self._session.commit()
