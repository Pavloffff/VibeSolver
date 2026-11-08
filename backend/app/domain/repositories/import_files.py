from typing import Protocol

from app.domain.entities import StoredSnapshotFile


class ImportFileRepository(Protocol):
    def upsert_file(
        self,
        source_id: int,
        branch: str,
        path: str,
        size_bytes: int,
        storage_key: str,
        content_hash: str,
    ) -> None: ...


class SourceSnapshotRepository(Protocol):
    def create_snapshot(
        self,
        source_id: int,
        import_id: int | None,
        files: list[dict[str, object]],
        source_revision: dict[str, object],
    ) -> int: ...

    def latest_snapshot_files(self, source_id: int) -> list[StoredSnapshotFile]: ...

    def snapshot_files(self, snapshot_id: int) -> list[StoredSnapshotFile]: ...
