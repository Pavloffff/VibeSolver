import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any

DOCUMENT_PARSER_VERSION = "document-registry-v1"
DOCUMENT_CHUNKER_VERSION = "heading-aware-v1"
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_CHUNK_CHARACTERS = 12_000
LINE_OVERLAP = 4
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True, slots=True)
class DocumentationChunk:
    path: str
    content_hash: str
    start_line: int
    end_line: int
    section: str
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DocumentationFileResult:
    chunks: list[DocumentationChunk]
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentParser:
    name: str
    parse_text: Callable[[str], str]


DOCUMENT_PARSER_REGISTRY: dict[str, DocumentParser] = {}


def register_document_parser(extensions: tuple[str, ...], parser: DocumentParser) -> None:
    for extension in extensions:
        normalized = extension.lower().lstrip(".")
        DOCUMENT_PARSER_REGISTRY[normalized] = parser


class _HtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._hidden_depth += 1
        elif tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self._chunks.append(data)

    def text(self) -> str:
        return "\n".join(
            line.strip() for line in "".join(self._chunks).splitlines() if line.strip()
        )


def _plain_text(value: str) -> str:
    return value


def _html_text(value: str) -> str:
    parser = _HtmlTextParser()
    parser.feed(value)
    parser.close()
    return parser.text()


_TEXT_PARSER = DocumentParser("plain-text", _plain_text)
register_document_parser(("md", "markdown", "txt", "rst", "adoc", "log"), _TEXT_PARSER)
register_document_parser(("html", "htm"), DocumentParser("html", _html_text))
DOCUMENT_PARSER_REGISTRY[""] = _TEXT_PARSER


def chunk_document_file(
    *,
    path: str,
    content: bytes,
    content_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DocumentationFileResult:
    if len(content) > MAX_DOCUMENT_BYTES:
        return DocumentationFileResult(
            [], f"File exceeds the document limit of {MAX_DOCUMENT_BYTES} bytes"
        )
    if b"\x00" in content:
        return DocumentationFileResult([], "Binary content is not indexed as documentation")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return DocumentationFileResult([], "File is not valid UTF-8 text")
    extension = PurePosixPath(path).suffix.lower().lstrip(".")
    parser = DOCUMENT_PARSER_REGISTRY.get(extension, _TEXT_PARSER)
    text = parser.parse_text(decoded)
    digest = content_hash or hashlib.sha256(content).hexdigest()
    base_metadata = {**(metadata or {}), "parser": parser.name}
    if extension in {"md", "markdown"}:
        chunks = _chunk_markdown(path, digest, text, base_metadata)
    else:
        chunks = _chunk_lines(path, digest, text, PurePosixPath(path).name, base_metadata)
    return DocumentationFileResult(chunks)


def _chunk_markdown(
    path: str, content_hash: str, text: str, metadata: dict[str, Any]
) -> list[DocumentationChunk]:
    lines = text.splitlines()
    sections: list[tuple[int, str, list[str]]] = []
    heading_stack: list[tuple[int, str]] = []
    current_title = PurePosixPath(path).name
    current_start = 1
    current_lines: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        heading = HEADING_PATTERN.match(line)
        if heading is None:
            current_lines.append(line)
            continue
        if current_lines:
            sections.append((current_start, current_title, current_lines))
        level = len(heading.group(1))
        title = heading.group(2).strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))
        current_title = " / ".join(item[1] for item in heading_stack)
        current_start = line_number
        current_lines = [line]
    if current_lines:
        sections.append((current_start, current_title, current_lines))
    chunks: list[DocumentationChunk] = []
    for start_line, title, section_lines in sections:
        chunks.extend(
            _split_document_section(path, content_hash, start_line, title, section_lines, metadata)
        )
    if not chunks and lines:
        chunks.extend(_chunk_lines(path, content_hash, text, PurePosixPath(path).name, metadata))
    return chunks


def _chunk_lines(
    path: str,
    content_hash: str,
    text: str,
    section: str,
    metadata: dict[str, Any],
) -> list[DocumentationChunk]:
    return _split_document_section(path, content_hash, 1, section, text.splitlines(), metadata)


def _split_document_section(
    path: str,
    content_hash: str,
    start_line: int,
    section: str,
    lines: list[str],
    metadata: dict[str, Any],
) -> list[DocumentationChunk]:
    if not lines:
        return []
    chunks: list[DocumentationChunk] = []
    start = 0
    while start < len(lines):
        end = start
        length = 0
        while end < len(lines) and length + len(lines[end]) + 1 <= MAX_CHUNK_CHARACTERS:
            length += len(lines[end]) + 1
            end += 1
        if end == start:
            end += 1
        chunks.append(
            DocumentationChunk(
                path=path,
                content_hash=content_hash,
                start_line=start_line + start,
                end_line=start_line + end - 1,
                section=section,
                content="\n".join(lines[start:end]),
                metadata=metadata,
            )
        )
        if end >= len(lines):
            break
        start = max(start + 1, end - LINE_OVERLAP)
    return chunks
