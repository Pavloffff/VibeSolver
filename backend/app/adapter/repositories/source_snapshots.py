import asyncio
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.domain.entities import StoredSnapshotFile
from app.domain.models import SourceSnapshot, SourceSnapshotFile
from app.domain.storage import S3Like


class SourceSnapshotSqlRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_snapshot(
        self,
        source_id: int,
        import_id: int | None,
        files: list[dict[str, object]],
        source_revision: dict[str, object],
    ) -> int:
        stable_files = sorted(
            (
                {
                    "branch": str(file["branch"]),
                    "path": str(file["path"]),
                    "content_hash": str(file["content_hash"]),
                }
                for file in files
            ),
            key=lambda item: (item["branch"], item["path"]),
        )
        content_hash = hashlib.sha256(
            json.dumps(stable_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        result = self._session.execute(
            text(
                "INSERT INTO source_snapshots "
                "(source_id, import_id, content_hash, source_revision) "
                "VALUES (:source_id, :import_id, :content_hash, CAST(:source_revision AS jsonb)) "
                "RETURNING id"
            ),
            {
                "source_id": source_id,
                "import_id": import_id,
                "content_hash": content_hash,
                "source_revision": json.dumps(source_revision, sort_keys=True),
            },
        )
        snapshot_id = int(result.scalar_one())
        for file in files:
            self._session.execute(
                text(
                    "INSERT INTO source_snapshot_files "
                    "(snapshot_id, branch, path, size_bytes, storage_key, content_hash, metadata_json) "
                    "VALUES (:snapshot_id, :branch, :path, :size_bytes, :storage_key, :content_hash, "
                    "CAST(:metadata_json AS jsonb))"
                ),
                {
                    "snapshot_id": snapshot_id,
                    "branch": file["branch"],
                    "path": file["path"],
                    "size_bytes": file["size_bytes"],
                    "storage_key": file["storage_key"],
                    "content_hash": file["content_hash"],
                    "metadata_json": json.dumps(file["metadata_json"], sort_keys=True),
                },
            )
        self._session.commit()
        if import_id is not None:
            self._session.execute(
                text(
                    "UPDATE project_indexes AS index_state SET status = 'stale', updated_at = now() "
                    "WHERE index_state.source_id = :source_id AND index_state.index_type = 'code' "
                    "AND index_state.active_run_id IS NOT NULL AND ("
                    "SELECT content_hash FROM source_snapshots WHERE id = ("
                    "SELECT snapshot_id FROM index_runs WHERE id = index_state.active_run_id"
                    ")) <> :content_hash"
                ),
                {"source_id": source_id, "content_hash": content_hash},
            )
            self._session.commit()
        return snapshot_id

    def latest_snapshot_files(self, source_id: int) -> list[StoredSnapshotFile]:
        snapshot_id = self._session.execute(
            text(
                "SELECT id FROM source_snapshots WHERE source_id = :source_id ORDER BY id DESC LIMIT 1"
            ),
            {"source_id": source_id},
        ).scalar_one_or_none()
        return self.snapshot_files(int(snapshot_id)) if snapshot_id is not None else []

    def snapshot_files(self, snapshot_id: int) -> list[StoredSnapshotFile]:
        rows = self._session.execute(
            text(
                "SELECT file.path, file.branch, file.storage_key, file.content_hash, "
                "file.size_bytes, file.metadata_json "
                "FROM source_snapshot_files AS file "
                "WHERE file.snapshot_id = :snapshot_id "
                "ORDER BY file.branch, file.path"
            ),
            {"snapshot_id": snapshot_id},
        ).all()
        return [
            StoredSnapshotFile(
                path=str(row.path),
                branch=str(row.branch),
                storage_key=str(row.storage_key),
                content_hash=str(row.content_hash),
                size_bytes=int(row.size_bytes),
                metadata=cast(dict[str, Any], row.metadata_json),
            )
            for row in rows
        ]


class SourceResourceSnapshotSqlRepository:
    def __init__(self, session: AsyncSession, s3: S3Like, bucket: str) -> None:
        self._session = session
        self._s3 = s3
        self._bucket = bucket

    async def create_snapshot(
        self, source_id: int, scope: str, resources: list[dict[str, Any]]
    ) -> int:
        snapshot_files: list[dict[str, Any]] = []
        for resource in resources:
            path = resource.get("path", resource.get("name"))
            config = resource.get("config")
            if not isinstance(config, dict):
                raise TypeError("resource storage metadata is missing")
            key = config.get("upload_key")
            if not isinstance(path, str) or not _safe_path(path):
                raise ValueError("resource path is not safe for indexing")
            if not isinstance(key, str) or not key.startswith(
                ("uploads/", f"resources/source-{source_id}/")
            ):
                raise ValueError("resource storage key is not valid for this project")
            response = await asyncio.to_thread(self._s3.get_object, Bucket=self._bucket, Key=key)
            body = response["Body"]
            content = body if isinstance(body, bytes) else await asyncio.to_thread(body.read)
            content_hash = hashlib.sha256(content).hexdigest()
            snapshot_files.append(
                {
                    "path": path,
                    "branch": "",
                    "size_bytes": len(content),
                    "storage_key": key,
                    "content_hash": content_hash,
                    "metadata_json": {
                        "scope": scope,
                        "resource_id": str(resource.get("id", "")),
                        "origin": config.get("origin", "uploaded"),
                        "content_type": config.get("content_type", "application/octet-stream"),
                        "text": config.get("text", False),
                    },
                }
            )
        file_fingerprint = [
            {"path": item["path"], "content_hash": item["content_hash"]}
            for item in sorted(snapshot_files, key=lambda value: str(value["path"]))
        ]
        content_hash = hashlib.sha256(
            json.dumps(file_fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshot = SourceSnapshot(
            source_id=source_id,
            import_id=None,
            content_hash=content_hash,
            source_revision={"scope": scope, "resources": file_fingerprint},
        )
        self._session.add(snapshot)
        await self._session.flush()
        for item in snapshot_files:
            self._session.add(SourceSnapshotFile(snapshot_id=snapshot.id, **item))
        await self._session.commit()
        return snapshot.id


def _safe_path(path: str) -> bool:
    candidate = PurePosixPath(path.replace("\\", "/"))
    return bool(path) and not candidate.is_absolute() and ".." not in candidate.parts
