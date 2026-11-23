from sqlalchemy import Select, and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Import,
    ImportState,
    IndexRun,
    ProjectIndex,
    Source,
    SourceSnapshot,
    SourceSnapshotFile,
)
from app.domain.source_browser import SourceBrowserEntry, SourceBrowserObject, SourceBrowserSnapshot


class SourceBrowserSqlRepository:
    async def code_snapshot_for_run(self, source_id: int, run_id: int) -> int | None:
        statement = (
            select(IndexRun.snapshot_id)
            .join(ProjectIndex, ProjectIndex.id == IndexRun.project_index_id)
            .where(
                IndexRun.id == run_id,
                ProjectIndex.source_id == source_id,
                ProjectIndex.index_type == "code",
            )
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_snapshot(self, source_id: int) -> SourceBrowserSnapshot | None:
        if await self._session.get(Source, source_id) is None:
            return None
        imported = (
            await self._session.execute(
                select(Import.id, SourceSnapshot)
                .outerjoin(
                    SourceSnapshot,
                    and_(
                        SourceSnapshot.import_id == Import.id, SourceSnapshot.source_id == source_id
                    ),
                )
                .where(Import.source_id == source_id, Import.status == ImportState.DONE.value)
                .order_by(Import.id.desc())
                .limit(1)
            )
        ).one_or_none()
        if imported is None:
            return SourceBrowserSnapshot(status="not_imported")
        snapshot = imported[1]
        if snapshot is None or snapshot.source_revision.get("legacy_import") is True:
            return SourceBrowserSnapshot(status="reimport_required")
        return SourceBrowserSnapshot(
            status="ready",
            snapshot_id=snapshot.id,
            branches=await self._branches(snapshot),
        )

    async def _branches(self, snapshot: SourceSnapshot) -> list[str]:
        file_branches = await self._session.scalars(
            select(SourceSnapshotFile.branch)
            .distinct()
            .where(SourceSnapshotFile.snapshot_id == snapshot.id)
        )
        metadata = snapshot.source_revision.get("branches")
        recorded = (
            {item for item in metadata if isinstance(item, str)}
            if isinstance(metadata, list)
            else set()
        )
        return sorted(recorded.union(file_branches)) or [""]

    def _successful_snapshots(self, source_id: int, snapshot_id: int) -> Select[SourceSnapshot]:
        return (
            select(SourceSnapshot)
            .join(Import, Import.id == SourceSnapshot.import_id)
            .where(
                SourceSnapshot.id == snapshot_id,
                SourceSnapshot.source_id == source_id,
                Import.source_id == source_id,
                Import.status == ImportState.DONE.value,
                SourceSnapshot.source_revision["legacy_import"]
                .as_string()
                .is_distinct_from("true"),
            )
        )

    async def has_branch(self, source_id: int, snapshot_id: int, branch: str) -> bool:
        snapshot = await self._session.scalar(self._successful_snapshots(source_id, snapshot_id))
        return snapshot is not None and branch in await self._branches(snapshot)

    async def list_entries(
        self, snapshot_id: int, branch: str, folder: str, offset: int, limit: int
    ) -> list[SourceBrowserEntry]:
        prefix = f"{folder}/" if folder else ""
        rows = await self._session.execute(
            text(
                """
                WITH paths AS (
                    SELECT substr(path, length(:prefix) + 1) AS remainder, size_bytes
                    FROM source_snapshot_files
                    WHERE snapshot_id = :snapshot_id AND branch = :branch
                      AND starts_with(path, :prefix) AND length(path) > length(:prefix)
                ), entries AS (
                    SELECT split_part(remainder, '/', 1) AS name,
                           strpos(remainder, '/') > 0 AS directory,
                           size_bytes
                    FROM paths
                )
                SELECT name, directory, CASE WHEN directory THEN NULL ELSE max(size_bytes) END AS size
                FROM entries
                GROUP BY name, directory
                ORDER BY directory DESC, name COLLATE "C"
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "snapshot_id": snapshot_id,
                "branch": branch,
                "prefix": prefix,
                "limit": limit,
                "offset": offset,
            },
        )
        return [
            SourceBrowserEntry(
                name=row.name,
                path=f"{prefix}{row.name}",
                kind="directory" if row.directory else "file",
                size_bytes=row.size,
            )
            for row in rows
        ]

    async def get_file(
        self, source_id: int, snapshot_id: int, branch: str, path: str
    ) -> SourceBrowserObject | None:
        snapshot = self._successful_snapshots(source_id, snapshot_id).subquery()
        row = (
            await self._session.execute(
                select(SourceSnapshotFile.storage_key, SourceSnapshotFile.size_bytes)
                .join(snapshot, SourceSnapshotFile.snapshot_id == snapshot.c.id)
                .where(SourceSnapshotFile.branch == branch, SourceSnapshotFile.path == path)
            )
        ).one_or_none()
        return (
            SourceBrowserObject(storage_key=row.storage_key, size_bytes=row.size_bytes)
            if row
            else None
        )
