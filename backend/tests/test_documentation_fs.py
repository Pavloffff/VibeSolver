from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from app.usecase.documentation_fs import (
    DocumentationPathError,
    archive_root_name,
    is_supported_archive,
    normalize_documentation_path,
    unpack_archive,
)
from app.usecase.project_resources import ProjectResourceUsecase


def test_normalize_documentation_path() -> None:
    assert normalize_documentation_path("manuals/setup.md") == "manuals/setup.md"
    for path in ("/manuals/setup.md", "../secret.md", "a/../../secret.md", "C:/secret.md", "a\\..\\secret.md"):
        with pytest.raises(DocumentationPathError):
            normalize_documentation_path(path)


def test_reserved_source_directories_are_case_insensitive() -> None:
    with pytest.raises(DocumentationPathError, match="reserved"):
        normalize_documentation_path("confluence/notes.md", local=True)
    assert normalize_documentation_path("Confluence/notes.md", local=False) == "Confluence/notes.md"


def test_extensionless_files_are_editable_text() -> None:
    assert ProjectResourceUsecase._is_editable_text({"type": "file", "name": "LICENSE", "config": {}})
    assert ProjectResourceUsecase._is_editable_text({"type": "file", "name": "LICENSE", "config": {"content_type": "application/octet-stream"}})


def test_archive_root_name_removes_supported_suffixes() -> None:
    assert archive_root_name("api-docs.tar.gz") == "api-docs"
    assert archive_root_name("manual.zip") == "manual"
    assert archive_root_name("manual.tar") == "manual"


def test_unpack_zip_preserves_paths_under_archive_folder() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("v1/openapi.md", "# API")
    result = unpack_archive("api-docs.zip", buffer.getvalue(), 1024)
    assert result == {"api-docs/v1/openapi.md": b"# API"}
    assert is_supported_archive(buffer.getvalue())


def test_archive_is_detected_without_filename_extension() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("LICENSE", "terms")
    assert unpack_archive("docs", buffer.getvalue(), 1024) == {"docs/LICENSE": b"terms"}


def test_unpack_zip_rejects_traversal() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../secret.md", "secret")
    with pytest.raises(DocumentationPathError, match="unsafe"):
        unpack_archive("docs.zip", buffer.getvalue(), 1024)


def test_unpack_tar_gz_preserves_paths() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        body = b"# Guide"
        info = tarfile.TarInfo("guide.md")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    assert unpack_archive("manual.tar.gz", buffer.getvalue(), 1024) == {
        "manual/guide.md": b"# Guide"
    }


def test_unpack_archive_enforces_expanded_size() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("large.md", "0123456789")
    with pytest.raises(DocumentationPathError, match="size limit"):
        unpack_archive("docs.zip", buffer.getvalue(), 5)
