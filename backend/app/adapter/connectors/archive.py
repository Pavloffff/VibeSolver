import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, ClassVar

from app.adapter.config import get_settings
from app.adapter.connectors.base import BaseConnector
from app.adapter.connectors.exclusions import (
    DEFAULT_MAX_FILE_SIZE,
    EXCLUDED_DIRS,
    is_excluded,
    parse_gitignore,
)
from app.adapter.s3 import make_s3_client
from app.domain.entities import ConfigField, ConfigValidationError, RawItem

ZIP_MAGIC = b"PK"
GZIP_MAGIC = b"\x1f\x8b"
COPY_CHUNK_BYTES = 1024 * 1024


class ArchiveConnector(BaseConnector):
    type: ClassVar[str] = "archive"
    ready: ClassVar[bool] = True
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            name="upload_key",
            label="Archive file",
            kind="file",
            required=True,
            hint="Upload a .zip or .tar.gz with the project sources",
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        upload_key = config.get("upload_key")
        if not isinstance(upload_key, str) or not upload_key.strip():
            raise ConfigValidationError("archive source config requires a non-empty 'upload_key'")

    def fetch_snapshot(
        self, config: dict[str, Any], work_dir: str | None = None
    ) -> Iterator[RawItem]:
        upload_key = str(config.get("upload_key", "")).strip()
        settings = get_settings()
        s3 = make_s3_client(settings)
        response = s3.get_object(Bucket=settings.s3_bucket_raw, Key=upload_key)
        body: bytes = response["Body"].read()
        if work_dir is not None:
            base = Path(work_dir)
            base.mkdir(parents=True, exist_ok=True)
            unpack_dir = base / "unpacked"
            unpack_dir.mkdir(parents=True, exist_ok=True)
            try:
                _unpack_archive(body, unpack_dir, settings.max_archive_unpacked_bytes)
                yield from _walk_snapshot(unpack_dir)
            finally:
                shutil.rmtree(unpack_dir, ignore_errors=True)
            return
        with tempfile.TemporaryDirectory() as tmp:
            unpack_dir = Path(tmp) / "unpacked"
            unpack_dir.mkdir()
            _unpack_archive(body, unpack_dir, settings.max_archive_unpacked_bytes)
            yield from _walk_snapshot(unpack_dir)


def _unpack_archive(body: bytes, target: Path, max_unpacked_bytes: int) -> None:
    if body.startswith(ZIP_MAGIC):
        _unpack_zip(body, target, max_unpacked_bytes)
    elif body.startswith(GZIP_MAGIC):
        _unpack_tar(body, target, max_unpacked_bytes)
    else:
        raise RuntimeError("failed to unpack archive: unknown format")


def _safe_member_target(root: Path, name: str) -> Path:
    member_path = PurePosixPath(name.replace("\\", "/"))
    if (
        member_path.is_absolute()
        or PureWindowsPath(name).is_absolute()
        or bool(PureWindowsPath(name).drive)
        or ".." in member_path.parts
    ):
        raise RuntimeError("failed to unpack archive: unsafe path")
    root_resolved = root.resolve()
    target = root_resolved.joinpath(*member_path.parts).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise RuntimeError("failed to unpack archive: unsafe path") from exc
    return target


def _unpack_zip(body: bytes, target: Path, max_unpacked_bytes: int) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            written = 0
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member_target = _safe_member_target(target, info.filename)
                member_target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, member_target.open("wb") as dest:
                    while True:
                        chunk = source.read(COPY_CHUNK_BYTES)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_unpacked_bytes:
                            raise RuntimeError("failed to unpack archive: size limit exceeded")
                        dest.write(chunk)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("failed to unpack archive: invalid archive data") from exc


def _unpack_tar(body: bytes, target: Path, max_unpacked_bytes: int) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
            written = 0
            for member in archive:
                if not member.isfile():
                    continue
                written += member.size
                if written > max_unpacked_bytes:
                    raise RuntimeError("failed to unpack archive: size limit exceeded")
                member_target = _safe_member_target(target, member.name)
                member_target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    continue
                with member_target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("failed to unpack archive: invalid archive data") from exc


def _root_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    return parse_gitignore(gitignore.read_text(encoding="utf-8", errors="replace"))


def _walk_snapshot(root: Path) -> Iterator[RawItem]:
    patterns = _root_gitignore_patterns(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS)
        for filename in sorted(filenames):
            if filename == ".gitignore":
                continue
            full = Path(dirpath) / filename
            rel = full.relative_to(root).as_posix()
            size = full.stat().st_size
            if is_excluded(rel, patterns, DEFAULT_MAX_FILE_SIZE, size):
                continue
            content = full.read_bytes()
            yield RawItem(
                path=rel,
                content=content,
                meta={
                    "size": size,
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
            )
