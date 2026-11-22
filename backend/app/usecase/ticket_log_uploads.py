from __future__ import annotations


class TicketLogUploadError(ValueError):
    pass


ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
GZIP_SIGNATURE = b"\x1f\x8b"


def validate_log_archive_upload(
    filename: str, data: bytes, max_upload_bytes: int
) -> tuple[str, int]:
    if len(data) > max_upload_bytes:
        raise TicketLogUploadError("archive upload is too large")

    normalized_filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not normalized_filename or len(normalized_filename) > 255:
        raise TicketLogUploadError("archive filename is empty or too long")
    if any(ord(char) < 32 for char in normalized_filename):
        raise TicketLogUploadError("archive filename contains invalid characters")

    suffix = normalized_filename.casefold()
    is_zip_name = suffix.endswith(".zip")
    is_tar_gz_name = suffix.endswith(".tar.gz")
    is_zip_data = data.startswith(ZIP_SIGNATURES)
    is_gzip_data = data.startswith(GZIP_SIGNATURE)
    if is_zip_name and is_zip_data or is_tar_gz_name and is_gzip_data:
        return normalized_filename, len(data)
    raise TicketLogUploadError("unsupported archive format (expected matching .zip or .tar.gz)")
