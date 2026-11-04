import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from botocore.exceptions import ClientError

from app.domain.entities import RawItem, UnknownStorageStrategyError


@dataclass(slots=True)
class PersistedFile:
    path: str
    branch: str
    storage_key: str
    size_bytes: int
    content_hash: str


class S3Like(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> Mapping[str, Any]: ...

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, Any]: ...

    def head_object(self, *, Bucket: str, Key: str) -> Mapping[str, Any]: ...


class StorageStrategy(Protocol):
    def persist(
        self, source_id: int, items: Sequence[RawItem], s3: S3Like, bucket: str
    ) -> list[PersistedFile]: ...


def _object_exists(s3: S3Like, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except ClientError:
        return False
    return True


class GitReferenceStorage:
    def persist(
        self, source_id: int, items: Sequence[RawItem], s3: S3Like, bucket: str
    ) -> list[PersistedFile]:
        branches = sorted({str(item.meta.get("branch", "")) for item in items})
        commits: dict[str, str] = {}
        for item in items:
            branch = str(item.meta.get("branch", ""))
            commit_sha = item.meta.get("commit_sha")
            if branch and commit_sha is not None:
                commits[branch] = str(commit_sha)
        files = [
            {
                "path": item.path,
                "branch": str(item.meta.get("branch", "")),
                "blob_sha": str(item.meta.get("blob_sha", "")),
                "size": len(item.content),
            }
            for item in items
        ]
        files.sort(key=lambda file: (file["branch"], file["path"]))
        manifest = {
            "source_id": source_id,
            "branches": branches,
            "commits": commits,
            "files": files,
        }
        manifest_body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        snapshot_id = hashlib.sha256(manifest_body).hexdigest()
        key = f"manifests/source-{source_id}/{snapshot_id}.json"
        if not _object_exists(s3, bucket, key):
            s3.put_object(Bucket=bucket, Key=key, Body=manifest_body)
        return [
            PersistedFile(
                path=item.path,
                branch=str(item.meta.get("branch", "")),
                storage_key=key,
                size_bytes=len(item.content),
                content_hash=str(item.meta.get("blob_sha", "")),
            )
            for item in items
        ]


class FullCopyStorage:
    def persist(
        self, source_id: int, items: Sequence[RawItem], s3: S3Like, bucket: str
    ) -> list[PersistedFile]:
        persisted_files: list[PersistedFile] = []
        for item in items:
            branch = str(item.meta.get("branch", ""))
            content_hash = hashlib.sha256(item.content).hexdigest()
            key = f"files/source-{source_id}/{content_hash}.bin"
            if not _object_exists(s3, bucket, key):
                s3.put_object(Bucket=bucket, Key=key, Body=item.content)
            persisted_files.append(
                PersistedFile(
                    path=item.path,
                    branch=branch,
                    storage_key=key,
                    size_bytes=len(item.content),
                    content_hash=content_hash,
                )
            )
        return persisted_files


STORAGE_STRATEGY_REGISTRY: dict[str, type[StorageStrategy]] = {
    "git_reference": GitReferenceStorage,
    "full_copy": FullCopyStorage,
}

DEFAULT_STORAGE_STRATEGY: dict[str, str] = {
    "git": "git_reference",
    "local_folder": "full_copy",
}


def resolve_storage_strategy(source_type: str, source_config: dict[str, Any]) -> StorageStrategy:
    override = source_config.get("storage_strategy")
    strategy_key = str(override) if override is not None else None
    if strategy_key is None:
        strategy_key = DEFAULT_STORAGE_STRATEGY.get(source_type)
    if strategy_key is None:
        raise UnknownStorageStrategyError(source_type)
    strategy_class = STORAGE_STRATEGY_REGISTRY.get(strategy_key)
    if strategy_class is None:
        raise UnknownStorageStrategyError(strategy_key)
    return strategy_class()
