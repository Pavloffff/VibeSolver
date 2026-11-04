from typing import Protocol


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
