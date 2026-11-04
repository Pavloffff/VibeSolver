from uuid import uuid4

from app.domain.storage import S3Like


class UploadArchive:
    def __init__(self, s3: S3Like, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    def store(self, data: bytes) -> str:
        key = f"uploads/{uuid4().hex}"
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key
