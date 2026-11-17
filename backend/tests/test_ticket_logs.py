from __future__ import annotations

import io
import zipfile

import pytest

from app.usecase.ticket_logs import LogArchiveError, extract_log_archive


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def test_extracts_supported_text_logs_with_line_numbers_and_redaction() -> None:
    archive = make_zip(
        {
            "app.log": (
                b"2026-11-17T10:15:30Z ERROR request failed\n"
                b"Authorization: Bearer abc.def.ghi\n"
                b"user email: alice@example.com\n"
            )
        }
    )

    result = extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000)

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.path == "incident/app.log"
    assert (chunk.start_line, chunk.end_line) == (1, 3)
    assert chunk.timestamp == "2026-11-17T10:15:30Z"
    assert "Bearer [REDACTED]" in chunk.content
    assert "alice@example.com" not in chunk.content
    assert result.diagnostics == []


def test_skips_binary_and_unsupported_files_with_diagnostics() -> None:
    archive = make_zip(
        {
            "binary.log": b"\x00\x01\x02",
            "image.png": b"not a log",
            "bad-encoding.txt": b"\xff\xfe",
        }
    )

    result = extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000)

    assert result.chunks == []
    assert {item.path for item in result.diagnostics} == {
        "incident/binary.log",
        "incident/image.png",
        "incident/bad-encoding.txt",
    }


def test_rejects_archive_traversal_paths() -> None:
    archive = make_zip({"../outside.log": b"secret"})

    with pytest.raises(LogArchiveError, match="unsafe path"):
        extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000)


def test_rejects_archive_expansion_over_limit() -> None:
    archive = make_zip({"large.log": b"x" * 100})

    with pytest.raises(LogArchiveError, match="expanded size limit"):
        extract_log_archive("incident.zip", archive, max_unpacked_bytes=20)


def test_chunks_large_log_on_line_boundaries() -> None:
    archive = make_zip({"app.log": ("a" * 30 + "\n" + "b" * 30 + "\n").encode()})

    result = extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000, chunk_chars=40)

    assert [(chunk.start_line, chunk.end_line) for chunk in result.chunks] == [(1, 1), (2, 2)]


def test_decodes_windows_1251_logs_with_russian_text() -> None:
    archive = make_zip({"application.log": "Ошибка: не хватает памяти".encode("cp1251")})

    result = extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000)

    assert result.chunks[0].content == "Ошибка: не хватает памяти"
    assert result.chunks[0].encoding == "windows-1251"


def test_decodes_utf16_logs_from_bom() -> None:
    archive = make_zip({"application.log": "Ошибка OOM".encode("utf-16")})

    result = extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000)

    assert result.chunks[0].content == "Ошибка OOM"
    assert result.chunks[0].encoding == "utf-16"


def test_decodes_windows_1252_logs_with_latin_diacritics() -> None:
    archive = make_zip({"application.log": "café déjà vu".encode("cp1252")})

    result = extract_log_archive("incident.zip", archive, max_unpacked_bytes=10_000)

    assert result.chunks[0].content == "café déjà vu"
    assert result.chunks[0].encoding == "windows-1252"
