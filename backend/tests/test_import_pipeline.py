import hashlib
import io
import json
import zipfile
from collections.abc import Sequence
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.adapter.config import Settings
from app.adapter.storage import (
    DEFAULT_STORAGE_STRATEGY,
    STORAGE_STRATEGY_REGISTRY,
    FullCopyStorage,
    GitReferenceStorage,
    resolve_storage_strategy,
)
from app.domain.entities import RawItem, UnknownConnectorError, UnknownStorageStrategyError
from app.domain.storage import PersistedFile, S3Like, StorageStrategy
from app.usecase.import_pipeline import (
    STAGE_REGISTRY,
    FetchItems,
    ImportContext,
    PersistItems,
    PipelineStage,
    run_stages,
)

GIT_COMMIT = "c" * 40
BLOB_A = "b" * 40
BLOB_B = "d" * 40


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_keys: list[tuple[str, str]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> dict[str, Any]:
        self.objects[(Bucket, Key)] = Body
        self.put_keys.append((Bucket, Key))
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(body)}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        body = self.objects.get((Bucket, Key))
        if body is None:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        return {"ContentLength": len(body)}


class SpyStage(PipelineStage):
    def __init__(self, journal: list[str], name: str) -> None:
        self._journal = journal
        self._name = name

    def run(self, ctx: ImportContext) -> None:
        self._journal.append(self._name)
        ctx.items.append(RawItem(path=self._name, content=b"", meta={}))


class FakeImportFileRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str, str], dict[str, Any]] = {}

    def upsert_file(
        self,
        source_id: int,
        branch: str,
        path: str,
        size_bytes: int,
        storage_key: str,
        content_hash: str,
    ) -> None:
        self.rows[(source_id, branch, path)] = {
            "source_id": source_id,
            "branch": branch,
            "path": path,
            "size_bytes": size_bytes,
            "storage_key": storage_key,
            "content_hash": content_hash,
        }


@pytest.fixture
def archive_upload_key(monkeypatch: pytest.MonkeyPatch) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", b"alpha\n")
        archive.writestr("src/b.py", b"print(1)\n")
    s3 = FakeS3()
    key = "uploads/project"
    s3.put_object(Bucket="raw", Key=key, Body=buffer.getvalue())
    monkeypatch.setattr("app.adapter.connectors.archive.get_settings", lambda: Settings())
    monkeypatch.setattr("app.adapter.connectors.archive.make_s3_client", lambda settings: s3)
    return key


def git_items() -> list[RawItem]:
    return [
        RawItem(
            path="a.txt",
            content=b"alpha\n",
            meta={"branch": "main", "blob_sha": BLOB_A, "commit_sha": GIT_COMMIT},
        ),
        RawItem(
            path="src/b.py",
            content=b"print(1)\n",
            meta={"branch": "main", "blob_sha": BLOB_B, "commit_sha": GIT_COMMIT},
        ),
    ]


def index_by_path(files: Sequence[PersistedFile]) -> dict[str, PersistedFile]:
    return {file.path: file for file in files}


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_stage_registry_contract() -> None:
    assert isinstance(STAGE_REGISTRY, list)
    assert FetchItems in STAGE_REGISTRY
    assert PersistItems in STAGE_REGISTRY
    assert STAGE_REGISTRY.index(FetchItems) < STAGE_REGISTRY.index(PersistItems)
    for stage_class in STAGE_REGISTRY:
        assert issubclass(stage_class, PipelineStage)
        assert callable(stage_class().run)


def test_import_context_holds_source_and_items() -> None:
    ctx = ImportContext(source_id=3, source_type="git", source_config={"url": "https://x/y.git"})
    assert ctx.source_id == 3
    assert ctx.source_type == "git"
    assert ctx.source_config == {"url": "https://x/y.git"}
    assert ctx.items == []
    item = RawItem(path="a.txt", content=b"alpha\n", meta={})
    ctx.items.append(item)
    assert ctx.items == [item]


def test_run_stages_calls_each_stage_in_order() -> None:
    journal: list[str] = []
    ctx = ImportContext(source_id=1, source_type="git", source_config={})
    stages = [SpyStage(journal, "one"), SpyStage(journal, "two"), SpyStage(journal, "three")]
    run_stages(ctx, stages)
    assert journal == ["one", "two", "three"]
    assert [item.path for item in ctx.items] == ["one", "two", "three"]


def test_run_stages_reports_progress_after_each_stage() -> None:
    journal: list[str] = []
    ctx = ImportContext(source_id=1, source_type="git", source_config={})
    stages = [SpyStage(journal, "one"), SpyStage(journal, "two"), SpyStage(journal, "three")]
    progress: list[tuple[int, int]] = []
    run_stages(ctx, stages, on_stage_done=lambda done, total: progress.append((done, total)))
    assert journal == ["one", "two", "three"]
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_fetch_items_populates_context_from_archive(archive_upload_key: str) -> None:
    ctx = ImportContext(
        source_id=1,
        source_type="archive",
        source_config={"upload_key": archive_upload_key},
    )
    FetchItems().run(ctx)
    by_path = {item.path: item for item in ctx.items}
    assert set(by_path) == {"a.txt", "src/b.py"}
    assert by_path["a.txt"].content == b"alpha\n"
    assert by_path["src/b.py"].content == b"print(1)\n"
    assert by_path["a.txt"].meta["size"] == 6
    assert by_path["a.txt"].meta["sha256"] == sha256_hex(b"alpha\n")


def test_fetch_items_replaces_snapshot_on_refetch(archive_upload_key: str) -> None:
    ctx = ImportContext(
        source_id=1,
        source_type="archive",
        source_config={"upload_key": archive_upload_key},
    )
    FetchItems().run(ctx)
    FetchItems().run(ctx)
    assert len(ctx.items) == 2


def test_fetch_items_unknown_source_type_raises() -> None:
    ctx = ImportContext(source_id=1, source_type="nonexistent", source_config={})
    with pytest.raises(UnknownConnectorError):
        FetchItems().run(ctx)


def test_fake_s3_satisfies_s3_protocol() -> None:
    client: S3Like = FakeS3()
    client.put_object(Bucket="raw", Key="probe", Body=b"body")
    assert client.head_object(Bucket="raw", Key="probe")["ContentLength"] == 4
    assert client.get_object(Bucket="raw", Key="probe")["Body"].read() == b"body"
    with pytest.raises(ClientError):
        client.head_object(Bucket="raw", Key="missing")


def test_git_reference_persists_single_manifest_object() -> None:
    s3 = FakeS3()
    persisted = GitReferenceStorage().persist(source_id=7, items=git_items(), s3=s3, bucket="raw")
    assert len(s3.put_keys) == 1
    bucket, key = s3.put_keys[0]
    assert bucket == "raw"
    assert key.startswith("manifests/source-7/")
    assert key.endswith(".json")
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    assert manifest["source_id"] == 7
    assert manifest["branches"] == ["main"]
    assert manifest["commits"] == {"main": GIT_COMMIT}
    assert [file["path"] for file in manifest["files"]] == ["a.txt", "src/b.py"]
    manifest_files = {file["path"]: file for file in manifest["files"]}
    assert manifest_files["a.txt"]["branch"] == "main"
    assert manifest_files["a.txt"]["blob_sha"] == BLOB_A
    assert manifest_files["a.txt"]["size"] == 6
    by_path = index_by_path(persisted)
    assert set(by_path) == {"a.txt", "src/b.py"}
    assert by_path["a.txt"].branch == "main"
    assert by_path["a.txt"].storage_key == key
    assert by_path["a.txt"].size_bytes == 6
    assert by_path["a.txt"].content_hash == BLOB_A
    assert by_path["src/b.py"].content_hash == BLOB_B


def test_git_reference_reimport_skips_unchanged_manifest() -> None:
    s3 = FakeS3()
    items = git_items()
    first = GitReferenceStorage().persist(source_id=7, items=items, s3=s3, bucket="raw")
    second = GitReferenceStorage().persist(source_id=7, items=items, s3=s3, bucket="raw")
    assert len(s3.put_keys) == 1
    assert [file.storage_key for file in second] == [file.storage_key for file in first]


def test_full_copy_uploads_every_item_as_object() -> None:
    s3 = FakeS3()
    items = [
        RawItem(path="a.txt", content=b"alpha\n", meta={"size": 6}),
        RawItem(path="src/b.py", content=b"print(1)\n", meta={}),
    ]
    persisted = FullCopyStorage().persist(source_id=7, items=items, s3=s3, bucket="raw")
    assert len(s3.put_keys) == 2
    hash_a = sha256_hex(b"alpha\n")
    hash_b = sha256_hex(b"print(1)\n")
    key_a = f"files/source-7/{hash_a}.bin"
    key_b = f"files/source-7/{hash_b}.bin"
    assert {(bucket, key) for bucket, key in s3.put_keys} == {("raw", key_a), ("raw", key_b)}
    assert s3.get_object(Bucket="raw", Key=key_a)["Body"].read() == b"alpha\n"
    assert s3.get_object(Bucket="raw", Key=key_b)["Body"].read() == b"print(1)\n"
    by_path = index_by_path(persisted)
    assert by_path["a.txt"].branch == ""
    assert by_path["a.txt"].storage_key == key_a
    assert by_path["a.txt"].content_hash == hash_a
    assert by_path["a.txt"].size_bytes == 6
    assert by_path["src/b.py"].branch == ""
    assert by_path["src/b.py"].storage_key == key_b
    assert by_path["src/b.py"].content_hash == hash_b
    assert by_path["src/b.py"].size_bytes == 9


def test_full_copy_dedupes_identical_content() -> None:
    s3 = FakeS3()
    items = [
        RawItem(path="one.txt", content=b"same\n", meta={}),
        RawItem(path="two.txt", content=b"same\n", meta={}),
    ]
    persisted = FullCopyStorage().persist(source_id=2, items=items, s3=s3, bucket="raw")
    assert len(s3.put_keys) == 1
    assert len({file.storage_key for file in persisted}) == 1
    assert {file.path for file in persisted} == {"one.txt", "two.txt"}


def test_full_copy_reimport_skips_unchanged_objects() -> None:
    s3 = FakeS3()
    items = [RawItem(path="a.txt", content=b"alpha\n", meta={})]
    FullCopyStorage().persist(source_id=7, items=items, s3=s3, bucket="raw")
    FullCopyStorage().persist(source_id=7, items=items, s3=s3, bucket="raw")
    assert len(s3.put_keys) == 1


def test_storage_strategy_registry_contains_strategies() -> None:
    assert isinstance(STORAGE_STRATEGY_REGISTRY, dict)
    assert STORAGE_STRATEGY_REGISTRY["git_reference"] is GitReferenceStorage
    assert STORAGE_STRATEGY_REGISTRY["full_copy"] is FullCopyStorage
    strategies: list[StorageStrategy] = [cls() for cls in STORAGE_STRATEGY_REGISTRY.values()]
    for strategy in strategies:
        assert callable(strategy.persist)


def test_default_storage_strategy_mapping() -> None:
    assert DEFAULT_STORAGE_STRATEGY["git"] == "git_reference"
    assert DEFAULT_STORAGE_STRATEGY["archive"] == "full_copy"
    for strategy_key in DEFAULT_STORAGE_STRATEGY.values():
        assert strategy_key in STORAGE_STRATEGY_REGISTRY


def test_resolve_storage_strategy_uses_defaults() -> None:
    assert isinstance(resolve_storage_strategy("git", {}), GitReferenceStorage)
    assert isinstance(resolve_storage_strategy("archive", {}), FullCopyStorage)


def test_resolve_storage_strategy_prefers_source_config_override() -> None:
    strategy = resolve_storage_strategy("git", {"storage_strategy": "full_copy"})
    assert isinstance(strategy, FullCopyStorage)


def test_resolve_storage_strategy_rejects_unknown_strategy() -> None:
    with pytest.raises(UnknownStorageStrategyError) as excinfo:
        resolve_storage_strategy("git", {"storage_strategy": "bogus"})
    assert excinfo.value.strategy_key == "bogus"


def test_resolve_storage_strategy_rejects_source_type_without_default() -> None:
    with pytest.raises(UnknownStorageStrategyError) as excinfo:
        resolve_storage_strategy("svn", {})
    assert excinfo.value.strategy_key == "svn"


def test_persist_items_records_each_file_row() -> None:
    repository = FakeImportFileRepository()
    s3 = FakeS3()
    ctx = ImportContext(
        source_id=5,
        source_type="archive",
        source_config={},
        items=[
            RawItem(path="a.txt", content=b"alpha\n", meta={}),
            RawItem(path="src/b.py", content=b"print(1)\n", meta={}),
        ],
    )
    stage = PersistItems(repository=repository, s3=s3, bucket="raw", strategy=FullCopyStorage())
    stage.run(ctx)
    assert set(repository.rows) == {(5, "", "a.txt"), (5, "", "src/b.py")}
    hash_a = sha256_hex(b"alpha\n")
    row = repository.rows[(5, "", "a.txt")]
    assert row["size_bytes"] == 6
    assert row["storage_key"] == f"files/source-5/{hash_a}.bin"
    assert row["content_hash"] == hash_a


def test_persist_items_rerun_keeps_single_row_per_file() -> None:
    repository = FakeImportFileRepository()
    s3 = FakeS3()
    ctx = ImportContext(
        source_id=5,
        source_type="archive",
        source_config={},
        items=[RawItem(path="a.txt", content=b"alpha\n", meta={})],
    )
    stage = PersistItems(repository=repository, s3=s3, bucket="raw", strategy=FullCopyStorage())
    stage.run(ctx)
    stage.run(ctx)
    assert len(repository.rows) == 1
    assert len(s3.put_keys) == 1


def test_persist_items_resolves_default_strategy_for_source_type() -> None:
    repository = FakeImportFileRepository()
    s3 = FakeS3()
    ctx = ImportContext(
        source_id=5,
        source_type="archive",
        source_config={},
        items=[RawItem(path="a.txt", content=b"alpha\n", meta={})],
    )
    PersistItems(repository=repository, s3=s3, bucket="raw").run(ctx)
    hash_a = sha256_hex(b"alpha\n")
    assert repository.rows[(5, "", "a.txt")]["storage_key"] == f"files/source-5/{hash_a}.bin"


def test_persist_items_strategy_override_from_source_config() -> None:
    repository = FakeImportFileRepository()
    s3 = FakeS3()
    ctx = ImportContext(
        source_id=9,
        source_type="git",
        source_config={"storage_strategy": "full_copy"},
        items=[
            RawItem(
                path="a.txt",
                content=b"alpha\n",
                meta={"branch": "main", "blob_sha": BLOB_A, "commit_sha": GIT_COMMIT},
            ),
        ],
    )
    PersistItems(repository=repository, s3=s3, bucket="raw").run(ctx)
    hash_a = sha256_hex(b"alpha\n")
    row = repository.rows[(9, "main", "a.txt")]
    assert row["storage_key"] == f"files/source-9/{hash_a}.bin"
    assert row["content_hash"] == hash_a
