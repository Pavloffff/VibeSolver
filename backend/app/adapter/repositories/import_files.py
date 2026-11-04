from sqlalchemy import text
from sqlalchemy.orm import Session


class ImportFileSqlRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_file(
        self,
        source_id: int,
        branch: str,
        path: str,
        size_bytes: int,
        storage_key: str,
        content_hash: str,
    ) -> None:
        stmt = text(
            "INSERT INTO imported_files "
            "(source_id, branch, path, size_bytes, storage_key, content_hash) "
            "VALUES (:source_id, :branch, :path, :size_bytes, :storage_key, :content_hash) "
            "ON CONFLICT (source_id, branch, path) DO UPDATE SET "
            "size_bytes = EXCLUDED.size_bytes, "
            "storage_key = EXCLUDED.storage_key, "
            "content_hash = EXCLUDED.content_hash"
        )
        self._session.execute(
            stmt,
            {
                "source_id": source_id,
                "branch": branch,
                "path": path,
                "size_bytes": size_bytes,
                "storage_key": storage_key,
                "content_hash": content_hash,
            },
        )
        self._session.commit()
