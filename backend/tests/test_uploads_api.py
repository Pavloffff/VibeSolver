import io
import tarfile
import zipfile
from typing import Any

import pytest
from botocore.exceptions import ClientError
from httpx import AsyncClient

from app.adapter.config import Settings


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

    def head_bucket(self, *, Bucket: str) -> dict[str, Any]:
        return {}

    def create_bucket(self, *, Bucket: str) -> dict[str, Any]:
        return {}


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.txt", b"alpha\n")
        archive.writestr("src/b.py", b"print(1)\n")
    return buffer.getvalue()


def build_tar_gz() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in (("a.txt", b"alpha\n"), ("src/b.py", b"print(1)\n")):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    s3 = FakeS3()
    monkeypatch.setattr("app.handler.routes.uploads.make_s3_client", lambda settings: s3)
    return s3


async def test_upload_zip_returns_201_with_key(
    api_client: AsyncClient, fake_s3: FakeS3
) -> None:
    response = await api_client.post(
        "/api/v1/uploads",
        files={"file": ("project.zip", build_zip(), "application/zip")},
    )
    assert response.status_code == 201
    upload_key = response.json()["upload_key"]
    assert isinstance(upload_key, str)
    assert upload_key.startswith("uploads/")
    assert ("raw", upload_key) in fake_s3.objects
    assert fake_s3.objects[("raw", upload_key)] == build_zip()


async def test_upload_tar_gz_returns_201_with_key(
    api_client: AsyncClient, fake_s3: FakeS3
) -> None:
    response = await api_client.post(
        "/api/v1/uploads",
        files={"file": ("project.tar.gz", build_tar_gz(), "application/gzip")},
    )
    assert response.status_code == 201
    upload_key = response.json()["upload_key"]
    assert upload_key.startswith("uploads/")
    assert ("raw", upload_key) in fake_s3.objects


async def test_upload_empty_zip_returns_201(
    api_client: AsyncClient, fake_s3: FakeS3
) -> None:
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w"):
        pass
    response = await api_client.post(
        "/api/v1/uploads",
        files={"file": ("empty.zip", empty.getvalue(), "application/zip")},
    )
    assert response.status_code == 201


async def test_upload_too_large_returns_413(
    api_client: AsyncClient, fake_s3: FakeS3, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.handler.routes.uploads.get_settings",
        lambda: Settings(max_upload_bytes=4),
    )
    response = await api_client.post(
        "/api/v1/uploads",
        files={"file": ("project.zip", build_zip(), "application/zip")},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "upload too large"
    assert fake_s3.objects == {}


async def test_upload_bad_magic_returns_422(
    api_client: AsyncClient, fake_s3: FakeS3
) -> None:
    response = await api_client.post(
        "/api/v1/uploads",
        files={"file": ("project.zip", b"notarchive", "application/zip")},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported archive format (expected .zip or .tar.gz)"
    assert fake_s3.objects == {}
