import hashlib
import io
import tarfile
import zipfile
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.adapter.config import Settings
from app.adapter.connectors.archive import ArchiveConnector
from app.domain.entities import ConfigValidationError

ARCHIVE_FILES: dict[str, bytes] = {
    "a.txt": b"alpha\n",
    "src/b.py": b"print(1)\n",
    "img.bin": b"\x89PNG" + b"\x00" * 32,
    "node_modules/pkg.js": b"module.exports = 1\n",
    ".git/config": b"[core]\n",
    ".gitignore": b"ignored.log\n",
    "ignored.log": b"log line\n",
}


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> dict[str, Any]:
        self.objects[(Bucket, Key)] = Body
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


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def build_tar_gz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def mount_archive(
    monkeypatch: pytest.MonkeyPatch, body: bytes, settings: Settings | None = None
) -> str:
    s3 = FakeS3()
    key = "uploads/fixture"
    s3.put_object(Bucket="raw", Key=key, Body=body)
    active = settings if settings is not None else Settings()
    monkeypatch.setattr("app.adapter.connectors.archive.get_settings", lambda: active)
    monkeypatch.setattr("app.adapter.connectors.archive.make_s3_client", lambda settings_arg: s3)
    return key


def assert_snapshot_items(items: list[Any]) -> None:
    by_path = {item.path: item for item in items}
    assert set(by_path) == {"a.txt", "src/b.py"}
    for rel in ("a.txt", "src/b.py"):
        expected = ARCHIVE_FILES[rel]
        item = by_path[rel]
        assert "\\" not in item.path
        assert item.content == expected
        assert item.meta["size"] == len(expected)
        assert item.meta["sha256"] == hashlib.sha256(expected).hexdigest()


def test_archive_descriptor_has_file_kind_field() -> None:
    fields = ArchiveConnector.config_fields
    assert fields[0].name == "upload_key"
    assert fields[0].kind == "file"
    assert fields[0].required is True


def test_archive_validate_config_requires_upload_key() -> None:
    connector = ArchiveConnector()
    connector.validate_config({"upload_key": "uploads/abc"})
    for invalid in ({}, {"upload_key": ""}, {"upload_key": "   "}, {"upload_key": 1}):
        with pytest.raises(ConfigValidationError):
            connector.validate_config(invalid)


def test_archive_fetch_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    key = mount_archive(monkeypatch, build_zip(ARCHIVE_FILES))
    items = list(ArchiveConnector().fetch_snapshot({"upload_key": key}))
    assert_snapshot_items(items)


def test_archive_fetch_empty_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    key = mount_archive(monkeypatch, build_zip({}))
    assert list(ArchiveConnector().fetch_snapshot({"upload_key": key})) == []


def test_archive_fetch_tar_gz(monkeypatch: pytest.MonkeyPatch) -> None:
    key = mount_archive(monkeypatch, build_tar_gz(ARCHIVE_FILES))
    items = list(ArchiveConnector().fetch_snapshot({"upload_key": key}))
    assert_snapshot_items(items)


def test_archive_fetch_unknown_magic(monkeypatch: pytest.MonkeyPatch) -> None:
    key = mount_archive(monkeypatch, b"notarchive at all")
    with pytest.raises(RuntimeError, match="unpack"):
        list(ArchiveConnector().fetch_snapshot({"upload_key": key}))


def test_archive_fetch_corrupt_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    key = mount_archive(monkeypatch, b"PK\x03\x04broken")
    with pytest.raises(RuntimeError, match="unpack"):
        list(ArchiveConnector().fetch_snapshot({"upload_key": key}))


def test_archive_fetch_rejects_oversized_unpacked(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(max_archive_unpacked_bytes=10)
    key = mount_archive(monkeypatch, build_zip(ARCHIVE_FILES), settings)
    with pytest.raises(RuntimeError, match="size limit"):
        list(ArchiveConnector().fetch_snapshot({"upload_key": key}))
