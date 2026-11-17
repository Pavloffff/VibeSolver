import pytest

from app.usecase.ticket_log_uploads import TicketLogUploadError, validate_log_archive_upload


def test_accepts_zip_with_matching_signature() -> None:
    filename, size = validate_log_archive_upload("logs.zip", b"PK\x03\x04payload", 100)

    assert filename == "logs.zip"
    assert size == 11


def test_accepts_tar_gz_with_matching_signature() -> None:
    filename, size = validate_log_archive_upload("logs.tar.gz", b"\x1f\x8bpayload", 100)

    assert filename == "logs.tar.gz"
    assert size == 9


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("logs.txt", b"PK\x03\x04payload"),
        ("logs.zip", b"\x1f\x8bpayload"),
        ("logs.tar.gz", b"PK\x03\x04payload"),
        ("logs.zip", b"not an archive"),
    ],
)
def test_rejects_unsupported_or_mismatched_archive(filename: str, data: bytes) -> None:
    with pytest.raises(TicketLogUploadError):
        validate_log_archive_upload(filename, data, 100)


def test_rejects_archives_over_compressed_size_limit() -> None:
    with pytest.raises(TicketLogUploadError, match="too large"):
        validate_log_archive_upload("logs.zip", b"PK\x03\x04payload", 4)


def test_strips_client_path_from_filename() -> None:
    filename, _ = validate_log_archive_upload(r"C:\fakepath\logs.zip", b"PK\x03\x04", 100)

    assert filename == "logs.zip"
