from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.adapter.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def make_s3_client(settings: Settings) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def ensure_bucket(client: "S3Client", bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def read_object_prefix(settings: Settings, key: str, max_bytes: int) -> bytes | None:
    try:
        client = make_s3_client(settings)
        body = client.get_object(Bucket=settings.s3_bucket_raw, Key=key)["Body"]
        try:
            data = bytearray()
            while len(data) < max_bytes:
                chunk = body.read(max_bytes - len(data))
                if not chunk:
                    break
                data.extend(chunk)
        finally:
            body.close()
    except (BotoCoreError, ClientError):
        return None
    return bytes(data)
