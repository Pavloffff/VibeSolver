from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Import


class ImportSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_for_source(self, source_id: int) -> Import | None:
        stmt = select(Import).where(Import.source_id == source_id).order_by(Import.id.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
