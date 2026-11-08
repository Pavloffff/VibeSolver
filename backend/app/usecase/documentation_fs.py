from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import PurePosixPath


class DocumentationPathError(ValueError):
    pass


RESERVED_ROOTS = frozenset({"confluence", "github wiki"})


def normalize_documentation_path(path: str, *, local: bool = True) -> str:
    normalized = path.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized:
        raise DocumentationPathError("documentation path must be relative")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DocumentationPathError("documentation path contains an unsafe segment")
    if any(any(ord(char) < 32 for char in part) for part in parts):
        raise DocumentationPathError("documentation path contains an invalid character")
    if local and parts[0].casefold() in RESERVED_ROOTS:
        raise DocumentationPathError(f"{parts[0]} is a reserved external source directory")
    return str(PurePosixPath(*parts))


def archive_root_name(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    lower = name.casefold()
    for suffix in (".tar.gz", ".tgz", ".zip", ".tar"):
        if lower.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if not name or name in {".", ".."}:
        raise DocumentationPathError("archive filename has no usable name")
    return name


def is_supported_archive(data: bytes) -> bool:
    payload = io.BytesIO(data)
    return zipfile.is_zipfile(payload) or tarfile.is_tarfile(io.BytesIO(data))


def unpack_archive(filename: str, data: bytes, max_unpacked_bytes: int) -> dict[str, bytes]:
    root = archive_root_name(filename)
    files: dict[str, bytes] = {}
    total = 0

    def add(path: str, content: bytes) -> None:
        nonlocal total
        safe_path = normalize_documentation_path(f"{root}/{path}", local=True)
        total += len(content)
        if total > max_unpacked_bytes:
            raise DocumentationPathError("archive expanded size limit exceeded")
        if safe_path in files:
            raise DocumentationPathError("archive contains duplicate file paths")
        files[safe_path] = content

    try:
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zip_archive:
                for zip_entry in zip_archive.infolist():
                    if zip_entry.is_dir():
                        continue
                    mode = zip_entry.external_attr >> 16
                    file_type = stat.S_IFMT(mode)
                    if file_type not in {0, stat.S_IFREG}:
                        raise DocumentationPathError("archive contains an unsafe special file")
                    with zip_archive.open(zip_entry) as zip_stream:
                        content = zip_stream.read(max_unpacked_bytes - total + 1)
                    add(zip_entry.filename, content)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar_archive:
                for tar_entry in tar_archive:
                    if tar_entry.isdir():
                        continue
                    if not tar_entry.isfile():
                        raise DocumentationPathError("archive contains an unsafe special file")
                    tar_stream = tar_archive.extractfile(tar_entry)
                    if tar_stream is None:
                        raise DocumentationPathError("archive contains an unreadable file")
                    with tar_stream:
                        content = tar_stream.read(max_unpacked_bytes - total + 1)
                    add(tar_entry.name, content)
    except DocumentationPathError:
        raise
    except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError) as exc:
        raise DocumentationPathError("unable to unpack documentation archive") from exc
    return files
