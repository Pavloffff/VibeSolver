from io import BytesIO
from stat import S_IFDIR, S_IFMT, S_IFREG
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo
from zlib import error as DeflateError

MAX_TICKET_TEXT_BYTES = 100_000
MAX_TICKET_ARCHIVE_BYTES = 1024 * 1024


class TicketArchiveError(ValueError):
    pass


def read_ticket_archive(body: bytearray) -> str:
    if not body.startswith(b"PK\x03\x04"):
        raise TicketArchiveError("Choose a valid ZIP archive.")
    try:
        with ZipFile(BytesIO(body)) as archive:
            entries = archive.infolist()
            if len(entries) > 256:
                raise TicketArchiveError("The ZIP archive contains too many entries.")
            text_entries: list[ZipInfo] = []
            for entry in entries:
                name = entry.orig_filename
                parts = name.removesuffix("/").split("/")
                kind = S_IFMT(entry.external_attr >> 16)
                if (
                    any(part in {"", ".", ".."} for part in parts)
                    or any(ord(char) < 32 for char in name)
                    or "\\" in name
                    or ":" in name
                    or entry.flag_bits & 1
                    or kind not in {0, S_IFDIR if entry.is_dir() else S_IFREG}
                ):
                    raise TicketArchiveError("The ZIP archive contains an unsupported entry.")
                if entry.is_dir() or parts[-1] in {".DS_Store", "Thumbs.db"}:
                    continue
                if parts[0] == "__MACOSX" and parts[-1].startswith("._"):
                    continue
                if parts[-1].lower().endswith(".txt"):
                    text_entries.append(entry)
                else:
                    raise TicketArchiveError("Include exactly one TXT file in the ZIP archive.")
            if len(text_entries) != 1:
                raise TicketArchiveError("Include exactly one TXT file in the ZIP archive.")
            entry = text_entries[0]
            if entry.file_size > MAX_TICKET_TEXT_BYTES:
                raise TicketArchiveError("The TXT file in the ZIP archive is too large.")
            if entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                raise TicketArchiveError("The ZIP archive uses unsupported compression.")
            with archive.open(entry) as member:
                content = member.read(MAX_TICKET_TEXT_BYTES + 1)
            if len(content) > MAX_TICKET_TEXT_BYTES:
                raise TicketArchiveError("The TXT file in the ZIP archive is too large.")
            if len(content) != entry.file_size:
                raise TicketArchiveError("The TXT file in the ZIP archive is incomplete.")
            decoded = content.decode("utf-8-sig")
            if "\x00" in decoded:
                raise TicketArchiveError("The TXT file must contain UTF-8 text.")
            return decoded
    except (BadZipFile, DeflateError, EOFError, RuntimeError, UnicodeError) as exc:
        raise TicketArchiveError("Choose a valid ZIP archive containing UTF-8 text.") from exc
