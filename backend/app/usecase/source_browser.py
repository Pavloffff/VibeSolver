import hashlib
import json
import re
from collections.abc import Awaitable, Callable

from app.domain.source_browser import (
    SourceBrowserFile,
    SourceBrowserRepository,
    SourceBrowserSnapshot,
    SourceBrowserTree,
)


class SourceBrowserNotFoundError(LookupError):
    pass


class SourceBrowserRequestError(ValueError):
    pass


class SourceBrowserUsecase:
    def __init__(
        self,
        repository: SourceBrowserRepository,
        read_bytes: Callable[[str, int], Awaitable[bytes | None]],
        preview_max_bytes: int,
        page_size: int,
    ) -> None:
        self._repository = repository
        self._read_bytes = read_bytes
        self._preview_max_bytes = preview_max_bytes
        self._page_size = page_size

    async def snapshot(self, source_id: int) -> SourceBrowserSnapshot:
        snapshot = await self._repository.latest_snapshot(source_id)
        if snapshot is None:
            raise SourceBrowserNotFoundError("project not found")
        return snapshot

    async def tree(
        self, source_id: int, snapshot_id: int, branch: str, folder: str, cursor: str | None
    ) -> SourceBrowserTree:
        self._validate_branch(branch)
        if folder:
            self._validate_path(folder)
        if not await self._repository.has_branch(source_id, snapshot_id, branch):
            raise SourceBrowserNotFoundError("source snapshot or branch not found")
        scope = hashlib.sha256(
            json.dumps([source_id, snapshot_id, branch, folder]).encode()
        ).hexdigest()
        offset = self._cursor_offset(cursor, scope)
        entries = await self._repository.list_entries(
            snapshot_id, branch, folder, offset, self._page_size + 1
        )
        if folder and not entries and offset == 0:
            raise SourceBrowserNotFoundError("source folder not found")
        next_cursor = (
            f"{scope}.{offset + self._page_size}" if len(entries) > self._page_size else None
        )
        return SourceBrowserTree(entries=entries[: self._page_size], next_cursor=next_cursor)

    async def file(
        self, source_id: int, snapshot_id: int, branch: str, path: str
    ) -> SourceBrowserFile:
        self._validate_branch(branch)
        self._validate_path(path)
        stored = await self._repository.get_file(source_id, snapshot_id, branch, path)
        if stored is None or not stored.storage_key.startswith(f"files/source-{source_id}/"):
            raise SourceBrowserNotFoundError("source file not found")
        if stored.size_bytes > self._preview_max_bytes:
            return SourceBrowserFile(path=path, status="too_large")
        data = await self._read_bytes(stored.storage_key, self._preview_max_bytes + 1)
        if data is None:
            return SourceBrowserFile(path=path, status="unavailable")
        if len(data) > self._preview_max_bytes:
            return SourceBrowserFile(path=path, status="too_large")
        if re.search(rb"[\x00-\x07\x0e-\x1f\x7f]", data):
            return SourceBrowserFile(path=path, status="binary")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return SourceBrowserFile(path=path, status="unsupported_encoding")
        return SourceBrowserFile(path=path, status="ready", content=content)

    @staticmethod
    def _cursor_offset(cursor: str | None, scope: str) -> int:
        if cursor is None:
            return 0
        actual_scope, _, offset = cursor.partition(".")
        if (
            actual_scope != scope
            or not offset.isascii()
            or not offset.isdecimal()
            or len(offset) > 18
        ):
            raise SourceBrowserRequestError("invalid source browser cursor")
        return int(offset)

    @staticmethod
    def _validate_branch(branch: str) -> None:
        if "\0" in branch:
            raise SourceBrowserRequestError("invalid source branch")

    @staticmethod
    def _validate_path(path: str) -> None:
        if "\0" in path or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
            raise SourceBrowserRequestError("source path must be relative to the snapshot")
