from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.usecase.documentation_fs import DocumentationPathError, unpack_archive


class LogArchiveError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LogChunk:
    path: str
    start_line: int
    end_line: int
    timestamp: str | None
    encoding: str
    content: str


@dataclass(frozen=True, slots=True)
class LogDiagnostic:
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class LogExtraction:
    chunks: list[LogChunk]
    diagnostics: list[LogDiagnostic]


_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_BEARER = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/-]+=*")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)"
    r"(\s*[=:]\s*)(\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

def extract_log_archive(
    filename: str,
    data: bytes,
    max_unpacked_bytes: int,
    chunk_chars: int = 4000,
) -> LogExtraction:
    if max_unpacked_bytes <= 0 or chunk_chars <= 0:
        raise ValueError("archive and chunk limits must be positive")
    try:
        files = unpack_archive(filename, data, max_unpacked_bytes)
    except DocumentationPathError as exc:
        message = str(exc)
        if "unsafe" in message or "path" in message:
            raise LogArchiveError("archive contains an unsafe path or special file") from exc
        if "expanded size limit" in message:
            raise LogArchiveError("archive expanded size limit exceeded") from exc
        raise LogArchiveError("unable to unpack log archive") from exc

    chunks: list[LogChunk] = []
    diagnostics: list[LogDiagnostic] = []
    for path, content in files.items():
        decoder = LOG_TEXT_DECODERS.get(PurePosixPath(path).suffix.casefold())
        if decoder is None:
            diagnostics.append(LogDiagnostic(path, "unsupported file type; skipped"))
            continue
        has_utf16_bom = content.startswith((b"\xff\xfe", b"\xfe\xff"))
        if b"\x00" in content and not has_utf16_bom:
            diagnostics.append(LogDiagnostic(path, "binary file; skipped"))
            continue
        try:
            text, encoding = decoder(content)
        except UnicodeDecodeError:
            diagnostics.append(LogDiagnostic(path, "file encoding is not supported; skipped"))
            continue
        if not text.strip():
            diagnostics.append(LogDiagnostic(path, "empty text file; skipped"))
            continue
        if _looks_binary(text):
            diagnostics.append(LogDiagnostic(path, "binary file; skipped"))
            continue
        chunks.extend(_chunk_text(path, text, encoding, chunk_chars))
    return LogExtraction(chunks, diagnostics)


def decode_log_text(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    windows_1251 = data.decode("cp1251")
    cyrillic_letters = sum(
        1
        for char in windows_1251
        if "CYRILLIC" in unicodedata.name(char, "") and unicodedata.category(char).startswith("L")
    )
    letters = sum(1 for char in windows_1251 if char.isalpha())
    if letters and cyrillic_letters / letters > 0.35:
        return windows_1251, "windows-1251"
    try:
        return data.decode("cp1252"), "windows-1252"
    except UnicodeDecodeError:
        return windows_1251, "windows-1251"


LOG_TEXT_DECODERS: dict[str, Callable[[bytes], tuple[str, str]]] = {
    ".log": decode_log_text,
    ".txt": decode_log_text,
    ".out": decode_log_text,
    ".err": decode_log_text,
    ".trace": decode_log_text,
    ".jsonl": decode_log_text,
}


def register_log_decoder(suffix: str, decoder: Callable[[bytes], tuple[str, str]]) -> None:
    normalized = suffix.casefold()
    if not normalized.startswith(".") or len(normalized) < 2:
        raise ValueError("log decoder suffix must start with a dot")
    LOG_TEXT_DECODERS[normalized] = decoder


def _looks_binary(text: str) -> bool:
    if not text:
        return False
    control_chars = sum(
        1 for char in text if ord(char) < 32 and char not in "\t\n\r\f\b"
    )
    return control_chars / len(text) > 0.01


def _chunk_text(path: str, text: str, encoding: str, chunk_chars: int) -> list[LogChunk]:
    lines = text.splitlines()
    chunks: list[LogChunk] = []
    current: list[str] = []
    current_chars = 0
    start_line = 1
    last_line = 0

    def flush(end_line: int) -> None:
        nonlocal current, current_chars
        if not current:
            return
        chunks.append(_make_chunk(path, start_line, end_line, encoding, "\n".join(current)))
        current = []
        current_chars = 0

    for line_number, line in enumerate(lines, start=1):
        if current and current_chars + 1 + len(line) > chunk_chars:
            flush(last_line)
        if len(line) > chunk_chars:
            if current:
                flush(last_line)
            for offset in range(0, len(line), chunk_chars):
                chunks.append(
                    _make_chunk(
                        path, line_number, line_number, encoding, line[offset : offset + chunk_chars]
                    )
                )
            start_line = line_number + 1
            last_line = line_number
            continue
        if not current:
            start_line = line_number
        current.append(line)
        current_chars += len(line) + (1 if len(current) > 1 else 0)
        last_line = line_number

    flush(last_line)
    return chunks


def _make_chunk(
    path: str, start_line: int, end_line: int, encoding: str, raw_content: str
) -> LogChunk:
    content = redact_sensitive_values(raw_content)
    timestamp_match = _TIMESTAMP.search(content)
    return LogChunk(
        path=path,
        start_line=start_line,
        end_line=end_line,
        timestamp=timestamp_match.group(0) if timestamp_match else None,
        encoding=encoding,
        content=content,
    )


def redact_sensitive_values(text: str) -> str:
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", text)
    return _EMAIL.sub("[REDACTED_EMAIL]", text)
