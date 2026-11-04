from typing import Protocol

from app.domain.models import Import


class ImportRepository(Protocol):
    async def latest_for_source(self, source_id: int) -> Import | None: ...
