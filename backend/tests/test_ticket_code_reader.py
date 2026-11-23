from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapter.repositories.source_browser import SourceBrowserSqlRepository
from app.domain.models import IndexRun, ProjectIndex, Source, SourceSnapshot
from app.domain.repositories.retrieval import SearchHit
from app.domain.source_browser import SourceBrowserFile
from app.usecase.ticket_code_reader import TicketCodeReader


def code_hit() -> SearchHit:
    return SearchHit("code", 19, "src/main.py", "release", 2, 2, None, "start()", 0.9)


async def test_reads_only_adjacent_lines_from_the_indexed_revision() -> None:
    snapshot = AsyncMock(return_value=7)
    read = AsyncMock(
        return_value=SourceBrowserFile(
            path="src/main.py",
            status="ready",
            content="first()\nstart()\npassword=secret\nlast()",
        )
    )
    reader = TicketCodeReader(snapshot, read, surrounding_lines=1)
    found = await reader.neighbors(3, code_hit(), 100)
    snapshot.assert_awaited_once_with(3, 19)
    read.assert_awaited_once_with(3, 7, "release", "src/main.py")
    assert [(hit.start_line, hit.end_line, hit.content) for hit in found] == [
        (1, 1, "first()"),
        (3, 3, "password=[REDACTED]"),
    ]
    assert all(hit.run_id == 19 and hit.branch == "release" for hit in found)


@pytest.mark.parametrize("snapshot_id,content", [(None, "x\nstart()\ny"), (7, "x\nother()\ny")])
async def test_unavailable_or_different_snapshot_never_substitutes_the_latest_file(
    snapshot_id: int | None,
    content: str,
) -> None:
    read = AsyncMock(
        return_value=SourceBrowserFile(path="src/main.py", status="ready", content=content)
    )
    reader = TicketCodeReader(AsyncMock(return_value=snapshot_id), read, surrounding_lines=8)
    assert await reader.neighbors(3, code_hit(), 100) == []
    if snapshot_id is None:
        read.assert_not_awaited()


async def test_looks_up_historical_code_revision_only_within_project(
    db_engine: AsyncEngine,
    clean_database: None,
) -> None:
    async with async_sessionmaker(db_engine)() as session:
        first = Source(type="archive", name="lab5", config={})
        other = Source(type="archive", name="other", config={})
        session.add_all([first, other])
        await session.flush()
        old = SourceSnapshot(source_id=first.id, content_hash="old")
        new = SourceSnapshot(source_id=first.id, content_hash="new")
        code = ProjectIndex(source_id=first.id, index_type="code")
        docs = ProjectIndex(source_id=first.id, index_type="documentation")
        session.add_all([old, new, code, docs])
        await session.flush()
        runs = [
            IndexRun(
                project_index_id=idx.id,
                snapshot_id=snap.id,
                status="completed",
                parser_version="1",
                chunker_version="1",
            )
            for idx, snap in ((code, old), (code, new), (docs, new))
        ]
        session.add_all(runs)
        await session.flush()
        reader = SourceBrowserSqlRepository(session)
        assert await reader.code_snapshot_for_run(first.id, runs[0].id) == old.id
        assert await reader.code_snapshot_for_run(other.id, runs[0].id) is None
        assert await reader.code_snapshot_for_run(first.id, runs[2].id) is None
