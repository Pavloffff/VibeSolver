import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.adapter.config import Settings
from app.adapter.db import to_sync_dsn
from app.adapter.repositories import ImportFileSqlRepository
from app.usecase.import_pipeline import FetchItems, ImportContext, PersistItems

PROJECT_FILES: dict[str, bytes] = {
    "a.txt": b"alpha\n",
    "src/b.py": b"print(1)\n",
}


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


def build_project_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def put_project(s3: FakeS3, key: str, files: dict[str, bytes]) -> None:
    s3.put_object(Bucket="raw", Key=key, Body=build_project_zip(files))


@pytest.fixture
def connector_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    s3 = FakeS3()
    monkeypatch.setattr("app.adapter.connectors.archive.get_settings", lambda: Settings())
    monkeypatch.setattr("app.adapter.connectors.archive.make_s3_client", lambda settings: s3)
    return s3


@pytest.fixture
def archive_upload_key(connector_s3: FakeS3) -> str:
    key = "uploads/project"
    put_project(connector_s3, key, PROJECT_FILES)
    return key


@pytest.fixture
def sync_engine(test_database_dsn: str) -> Iterator[Engine]:
    engine = create_engine(to_sync_dsn(test_database_dsn))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE sources CASCADE"))
    yield engine
    engine.dispose()


@pytest.fixture
def archive_source_id(sync_engine: Engine, archive_upload_key: str) -> int:
    with sync_engine.begin() as connection:
        result = connection.execute(
            text(
                "INSERT INTO sources (type, name, config) "
                "VALUES ('archive', 'fixture archive', CAST(:config AS jsonb)) RETURNING id"
            ),
            {"config": json.dumps({"upload_key": archive_upload_key})},
        )
        return int(result.scalar_one())


def run_import(session: Session, source_id: int, upload_key: str, s3: FakeS3) -> None:
    ctx = ImportContext(
        source_id=source_id,
        source_type="archive",
        source_config={"upload_key": upload_key},
    )
    FetchItems().run(ctx)
    PersistItems(repository=ImportFileSqlRepository(session), s3=s3, bucket="raw").run(ctx)


def select_imported_files(engine: Engine, source_id: int) -> list[Any]:
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "SELECT branch, path, size_bytes, storage_key, content_hash "
                "FROM imported_files WHERE source_id = :source_id"
            ),
            {"source_id": source_id},
        )
        return list(result.all())


def test_archive_full_copy_end_to_end(
    sync_engine: Engine, archive_source_id: int, archive_upload_key: str
) -> None:
    s3 = FakeS3()
    session_factory = sessionmaker(bind=sync_engine)
    with session_factory() as session:
        run_import(session, archive_source_id, archive_upload_key, s3)
    rows = select_imported_files(sync_engine, archive_source_id)
    assert len(rows) == 2
    by_path = {row.path: row for row in rows}
    assert set(by_path) == {"a.txt", "src/b.py"}
    for path, content in PROJECT_FILES.items():
        content_hash = hashlib.sha256(content).hexdigest()
        storage_key = f"files/source-{archive_source_id}/{content_hash}.bin"
        row = by_path[path]
        assert row.branch == ""
        assert row.size_bytes == len(content)
        assert row.storage_key == storage_key
        assert row.content_hash == content_hash
        assert s3.get_object(Bucket="raw", Key=storage_key)["Body"].read() == content


def test_reimport_upserts_rows_without_duplicates(
    sync_engine: Engine,
    archive_source_id: int,
    archive_upload_key: str,
    connector_s3: FakeS3,
) -> None:
    s3 = FakeS3()
    session_factory = sessionmaker(bind=sync_engine)
    with session_factory() as session:
        run_import(session, archive_source_id, archive_upload_key, s3)
        run_import(session, archive_source_id, archive_upload_key, s3)
        put_project(connector_s3, archive_upload_key, {**PROJECT_FILES, "a.txt": b"beta\n"})
        run_import(session, archive_source_id, archive_upload_key, s3)
    rows = select_imported_files(sync_engine, archive_source_id)
    assert len(rows) == 2
    by_path = {row.path: row for row in rows}
    hash_beta = hashlib.sha256(b"beta\n").hexdigest()
    hash_b = hashlib.sha256(b"print(1)\n").hexdigest()
    assert by_path["a.txt"].content_hash == hash_beta
    assert by_path["a.txt"].storage_key == f"files/source-{archive_source_id}/{hash_beta}.bin"
    assert by_path["src/b.py"].content_hash == hash_b
    assert by_path["src/b.py"].storage_key == f"files/source-{archive_source_id}/{hash_b}.bin"
    put_keys = [key for _, key in s3.put_keys]
    assert put_keys.count(f"files/source-{archive_source_id}/{hash_b}.bin") == 1
    assert f"files/source-{archive_source_id}/{hash_beta}.bin" in put_keys
    assert len(put_keys) == 3
