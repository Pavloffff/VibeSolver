from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.domain.entities import ImportSnapshot
from app.domain.models import Import, Source


class SourceSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, source_type: str, name: str, config: dict[str, Any]) -> Source:
        source = Source(type=source_type, name=name, config=config, enabled=True)
        self._session.add(source)
        await self._session.commit()
        await self._session.refresh(source)
        return source

    async def get_any(self, source_id: int) -> Source | None:
        return await self._session.get(Source, source_id)

    async def get_enabled(self, source_id: int) -> Source | None:
        source = await self._session.get(Source, source_id)
        if source is None or not source.enabled:
            return None
        return source

    async def set_enabled(self, source_id: int, enabled: bool) -> None:
        source = await self._session.get(Source, source_id)
        if source is None:
            return
        source.enabled = enabled
        await self._session.commit()

    async def list_enabled_with_last_import(self) -> list[tuple[Source, ImportSnapshot | None]]:
        latest_import = (
            select(Import.source_id, Import.status, Import.finished_at)
            .ext(distinct_on(Import.source_id))
            .order_by(Import.source_id, Import.id.desc())
            .subquery()
        )
        result = await self._session.execute(
            select(Source, latest_import.c.status, latest_import.c.finished_at)
            .outerjoin(latest_import, Source.id == latest_import.c.source_id)
            .where(Source.enabled.is_(True))
            .order_by(Source.id)
        )
        rows = result.all()
        return [
            (
                source,
                (
                    ImportSnapshot(
                        status=status,
                        progress=0,
                        error=None,
                        finished_at=finished_at,
                    )
                    if status is not None
                    else None
                ),
            )
            for source, status, finished_at in rows
        ]


class ImportSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_for_source(self, source_id: int) -> Import | None:
        stmt = (
            select(Import).where(Import.source_id == source_id).order_by(Import.id.desc()).limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


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
