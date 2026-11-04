from fastapi import APIRouter, HTTPException, UploadFile

from app.adapter.config import Settings, get_settings
from app.adapter.s3 import ensure_bucket, make_s3_client
from app.handler.schemas import UploadOut
from app.usecase.uploads import UploadArchive

router = APIRouter(prefix="/uploads", tags=["uploads"])

ZIP_MAGIC = b"PK"
GZIP_MAGIC = b"\x1f\x8b"
READ_CHUNK_BYTES = 1024 * 1024


def build_uploader(settings: Settings) -> UploadArchive:
    s3 = make_s3_client(settings)
    ensure_bucket(s3, settings.s3_bucket_raw)
    return UploadArchive(s3=s3, bucket=settings.s3_bucket_raw)


@router.post("", status_code=201, response_model=UploadOut)
async def upload_archive(file: UploadFile) -> UploadOut:
    settings = get_settings()
    data = await read_archive(file, settings.max_upload_bytes)
    uploader = build_uploader(settings)
    return UploadOut(upload_key=uploader.store(data))


async def read_archive(file: UploadFile, max_upload_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_upload_bytes:
            raise HTTPException(status_code=413, detail="upload too large")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(ZIP_MAGIC) and not data.startswith(GZIP_MAGIC):
        raise HTTPException(
            status_code=422, detail="unsupported archive format (expected .zip or .tar.gz)"
        )
    return data
