from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from test_retrieval_usecase import FakeIndexing, FakeModels, FakeSearch, FakeSources, _run_status

from app.adapter.repositories.material_generation import IndexSearchSqlRepository
from app.domain.repositories.material_generation import LiteralCodeMatch, RetrievedChunk
from app.usecase.retrieval import RetrievalUsecase

LITERAL = "/api/admin/GetAll"


async def test_exact_literal_focuses_on_the_registration_without_model_calls() -> None:
    line = f'router.get("{LITERAL}", list_members)'
    beginning = "arbitrary prefix " * 600 + "\n" + "other code\n" * 60
    content = beginning + line + "\n" + "other trailing code\n" * 80
    chunk = RetrievedChunk(
        11,
        "code",
        "server/routes.py",
        "release",
        120,
        120 + content.count("\n") - 1,
        None,
        content,
        {},
        1.0,
    )
    search = FakeSearch()
    search.search_code_literal = AsyncMock(
        return_value=[LiteralCodeMatch(chunk, len(beginning) + line.index(LITERAL))]
    )
    no_model_calls = Mock(side_effect=AssertionError("literal lookup must not run any models"))
    retrieval = RetrievalUsecase(
        FakeSources(),
        FakeIndexing([_run_status("code", "completed", 73)]),
        search,
        FakeModels(selection=None),
        no_model_calls,
        None,
        10,
    )

    hits = await retrieval.search_code_literal(17, LITERAL, top_k=50)

    search.search_code_literal.assert_awaited_once_with(17, 73, LITERAL, 8)
    no_model_calls.assert_not_called()
    hit = hits[0]
    assert (hit.run_id, hit.path, hit.branch) == (73, "server/routes.py", "release")
    assert len(hit.content) <= 1200 and line in hit.content
    assert hit.start_line is not None and hit.end_line is not None
    assert hit.start_line + hit.content.splitlines().index(line) == 181
    assert hit.end_line == hit.start_line + len(hit.content.splitlines()) - 1


@pytest.mark.parametrize("literal", ["/", "a", "/api\n/foo", "x" * 257])
async def test_literal_lookup_rejects_unusable_inputs_before_searching(literal: str) -> None:
    search = FakeSearch()
    search.search_code_literal = AsyncMock(
        side_effect=AssertionError("an invalid literal must not query the index")
    )
    retrieval = RetrievalUsecase(
        FakeSources(), FakeIndexing([]), search, FakeModels(), Mock(), None, 10
    )
    assert await retrieval.search_code_literal(17, literal) == []


async def _insert_run(connection: AsyncConnection, source_id: int, kind: str) -> int:
    project_index_id = int(
        (
            await connection.execute(
                text("""
                INSERT INTO project_indexes(source_id, index_type, status)
                VALUES (:source_id, :kind, 'completed')
                ON CONFLICT (source_id, index_type) DO UPDATE SET status = EXCLUDED.status
                RETURNING id
            """),
                {"source_id": source_id, "kind": kind},
            )
        ).scalar_one()
    )
    snapshot_id = int(
        (
            await connection.execute(
                text(
                    "INSERT INTO source_snapshots(source_id, content_hash) VALUES (:source_id, 'hash') RETURNING id"
                ),
                {"source_id": source_id},
            )
        ).scalar_one()
    )
    run_id = int(
        (
            await connection.execute(
                text("""
                INSERT INTO index_runs(project_index_id, snapshot_id, status, parser_version, chunker_version)
                VALUES (:index_id, :snapshot_id, 'completed', 'test', 'test') RETURNING id
            """),
                {"index_id": project_index_id, "snapshot_id": snapshot_id},
            )
        ).scalar_one()
    )
    await connection.execute(
        text("UPDATE project_indexes SET active_run_id = :run_id WHERE id = :index_id"),
        {"run_id": run_id, "index_id": project_index_id},
    )
    return run_id


async def test_sql_literal_matches_only_active_scoped_code_and_prioritizes_source(
    db_engine: AsyncEngine, git_source_id: int
) -> None:
    exact = "/api/users/Get%_All"
    async with db_engine.begin() as connection:
        other = int(
            (
                await connection.execute(
                    text(
                        "INSERT INTO sources (type,name,config) VALUES ('git','Other','{}') RETURNING id"
                    )
                )
            ).scalar_one()
        )
        outdated = await _insert_run(connection, git_source_id, "code")
        current = await _insert_run(connection, git_source_id, "code")
        documentation = await _insert_run(connection, git_source_id, "documentation")
        foreign = await _insert_run(connection, other, "code")

        await connection.execute(
            text("""
                INSERT INTO index_chunks(run_id, path, branch, content_hash, start_line, end_line, content)
                VALUES (:run, :path, 'main', 'chunk', 20, 20, :content)
            """),
            [
                {"run": outdated, "path": "old/routes.py", "content": f'route("{exact}")'},
                {"run": foreign, "path": "foreign/routes.py", "content": f'route("{exact}")'},
                {"run": documentation, "path": "docs/routes.md", "content": f'Use "{exact}".'},
                {"run": current, "path": "swagger.json", "content": f'"{exact}": {{}}'},
                {"run": current, "path": "tests/api.spec.ts", "content": f'get("{exact}")'},
                {
                    "run": current,
                    "path": "src/guessed.py",
                    "content": 'route("/api/users/GetZZAll")',
                },
                {"run": current, "path": "src/sibling.py", "content": f'route("{exact}/extra")'},
                {"run": current, "path": "config/route.toml", "content": f'path = "{exact}"'},
                {"run": current, "path": "src/actual.py", "content": f'route("{exact}", handler)'},
            ],
        )

    async with AsyncSession(db_engine) as session:
        repository = IndexSearchSqlRepository(session)
        assert await repository.search_code_literal(git_source_id, outdated, exact, 8) == []
        assert await repository.search_code_literal(git_source_id, documentation, exact, 8) == []
        assert await repository.search_code_literal(git_source_id, foreign, exact, 8) == []
        matches = await repository.search_code_literal(git_source_id, current, exact, 8)

    paths = [match.chunk.path for match in matches]
    assert set(paths[:2]) == {"config/route.toml", "src/actual.py"}
    assert set(paths[2:]) == {"swagger.json", "tests/api.spec.ts"}
    assert all(match.chunk.content[match.offset :].startswith(exact) for match in matches)


async def test_literal_lookup_bounds_one_very_long_line_around_full_literal() -> None:
    content = "a" * 4000 + f' "{LITERAL}" ' + "z" * 4000
    chunk = RetrievedChunk(9, "code", "routes.cs", "main", 42, 42, None, content, {}, 1.0)
    search = FakeSearch()
    search.search_code_literal = AsyncMock(
        return_value=[
            LiteralCodeMatch(chunk, -1),
            LiteralCodeMatch(chunk, content.index(LITERAL)),
        ]
    )
    retrieval = RetrievalUsecase(
        FakeSources(),
        FakeIndexing([_run_status("code", "completed", 1)]),
        search,
        FakeModels(selection=None),
        Mock(side_effect=AssertionError("literal lookup must not run any models")),
        None,
        10,
    )

    hits = await retrieval.search_code_literal(7, LITERAL)

    assert len(hits) == 1
    assert len(hits[0].content) == 1200
    assert LITERAL in hits[0].content
    assert hits[0].start_line == hits[0].end_line == 42
