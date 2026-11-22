from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapter.config import Settings
from app.domain.models import Import, Source, SourceSnapshot, SourceSnapshotFile
from app.domain.source_browser import SourceBrowserObject
from app.handler.app import create_app
from app.handler.routes import source_browser
from app.usecase.source_browser import SourceBrowserRequestError, SourceBrowserUsecase


async def test_source_browser_routes_expose_read_only_contract() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/openapi.json")
    paths = response.json()["paths"]
    prefix = "/api/v1/sources/{source_id}/source-browser"
    assert set(paths[prefix]) == {"get"}
    assert set(paths[f"{prefix}/{{snapshot_id}}/tree"]) == {"get"}
    assert set(paths[f"{prefix}/{{snapshot_id}}/file"]) == {"get"}


@pytest.mark.parametrize(
    ("recorded_size", "data", "expected", "reads"),
    [
        (3, b"abc", "ready", 1),
        (4, b"abcd", "too_large", 0),
        (0, b"abcd", "too_large", 1),
        (2, b"a\x00", "binary", 1),
        (1, b"\xff", "unsupported_encoding", 1),
        (1, None, "unavailable", 1),
    ],
)
async def test_source_preview_checks_size_before_and_after_bounded_reads(
    recorded_size: int, data: bytes | None, expected: str, reads: int
) -> None:
    repository = AsyncMock()
    repository.get_file.return_value = SourceBrowserObject(
        storage_key="files/source-1/hash.bin",
        size_bytes=recorded_size,
    )
    read_bytes = AsyncMock(return_value=data)
    browser = SourceBrowserUsecase(repository, read_bytes, 3, 1)
    result = await browser.file(1, 2, "main", "src/main.py")
    assert result.status == expected
    assert read_bytes.await_count == reads
    if reads:
        read_bytes.assert_awaited_once_with("files/source-1/hash.bin", 4)


async def test_source_file_rejects_traversal_before_lookup() -> None:
    repository = AsyncMock()
    browser = SourceBrowserUsecase(repository, AsyncMock(), 3, 1)
    with pytest.raises(SourceBrowserRequestError):
        await browser.file(1, 2, "main", "src/../README.md")
    repository.get_file.assert_not_awaited()


async def test_source_browser_scopes_tree_and_preview_to_completed_import(
    api_client: AsyncClient,
    db_engine: AsyncEngine,
    clean_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        project = Source(type="git", name="project", config={})
        other = Source(type="git", name="other", config={})
        session.add_all([project, other])
        await session.flush()

        success = Import(source_id=project.id, status="done")
        failed = Import(source_id=project.id, status="failed")
        legacy = Import(source_id=other.id, status="done")
        session.add_all([success, failed, legacy])
        await session.flush()

        snapshot = SourceSnapshot(source_id=project.id, import_id=success.id, content_hash="code")
        failed_snapshot = SourceSnapshot(
            source_id=project.id, import_id=failed.id, content_hash="failed"
        )
        docs_snapshot = SourceSnapshot(
            source_id=project.id, content_hash="docs", source_revision={"scope": "documentation"}
        )
        session.add_all([snapshot, failed_snapshot, docs_snapshot])
        await session.flush()

        storage_prefix = f"files/source-{project.id}/"
        for branch, path, key in [
            ("main", "src/code.py", "main"),
            ("main", "src/other.py", "other"),
            ("main", "README.md", "readme"),
            ("feature/one", "src/code.py", "feature"),
        ]:
            session.add(
                SourceSnapshotFile(
                    snapshot_id=snapshot.id,
                    branch=branch,
                    path=path,
                    size_bytes=4,
                    storage_key=f"{storage_prefix}{key}.bin",
                    content_hash=key,
                )
            )
        await session.commit()

    monkeypatch.setattr(
        source_browser, "get_settings", lambda: Settings(source_browser_page_size=1)
    )
    reads: list[str] = []

    def read_object(settings: object, key: str, max_bytes: int) -> bytes:
        reads.append(key)
        return b"text"

    monkeypatch.setattr(source_browser, "read_object_prefix", read_object)
    prefix = f"/api/v1/sources/{project.id}/source-browser"
    current = await api_client.get(prefix)
    assert current.json() == {
        "status": "ready",
        "snapshot_id": snapshot.id,
        "branches": ["feature/one", "main"],
    }
    legacy_result = await api_client.get(f"/api/v1/sources/{other.id}/source-browser")
    assert legacy_result.json()["status"] == "reimport_required"
    tree_url = f"{prefix}/{snapshot.id}/tree"
    first = (await api_client.get(tree_url, params={"branch": "main"})).json()
    assert [(entry["kind"], entry["path"]) for entry in first["entries"]] == [("directory", "src")]
    second = await api_client.get(
        tree_url, params={"branch": "main", "cursor": first["next_cursor"]}
    )
    assert [entry["path"] for entry in second.json()["entries"]] == ["README.md"]
    wrong_folder = await api_client.get(
        tree_url, params={"branch": "main", "folder": "src", "cursor": first["next_cursor"]}
    )
    assert wrong_folder.status_code == 422
    assert reads == []

    file_url = f"{prefix}/{snapshot.id}/file"
    query = {"branch": "feature/one", "path": "src/code.py"}
    foreign = await api_client.get(
        f"/api/v1/sources/{other.id}/source-browser/{snapshot.id}/file", params=query
    )
    assert foreign.status_code == 404
    assert reads == []
    file = await api_client.get(file_url, params=query)
    assert file.json()["content"] == "text"
    assert reads == [f"{storage_prefix}feature.bin"]
