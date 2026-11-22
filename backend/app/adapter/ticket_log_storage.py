from uuid import uuid4

from app.adapter.config import Settings
from app.adapter.s3 import ensure_bucket, make_s3_client
from app.domain.storage import S3Like


class TicketLogArchiveStorage:
    def __init__(self, s3: S3Like, bucket: str) -> None:
        self._s3 = s3
        self._bucket = bucket

    def store(self, source_id: int, ticket_id: int, filename: str, data: bytes) -> str:
        key = f"ticket-logs/source-{source_id}/ticket-{ticket_id}/{uuid4().hex}/{filename}"
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)


def build_ticket_log_storage(settings: Settings) -> TicketLogArchiveStorage:
    client = make_s3_client(settings)
    ensure_bucket(client, settings.s3_bucket_raw)
    return TicketLogArchiveStorage(client, settings.s3_bucket_raw)
