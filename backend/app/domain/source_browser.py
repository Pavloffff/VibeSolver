from typing import Literal, Protocol

from pydantic import BaseModel, Field


class SourceBrowserSnapshot(BaseModel):
    status: Literal["ready", "not_imported", "reimport_required"]
    snapshot_id: int | None = None
    branches: list[str] = Field(default_factory=list)


class SourceBrowserEntry(BaseModel):
    name: str
    path: str
    kind: Literal["directory", "file"]
    size_bytes: int | None


class SourceBrowserTree(BaseModel):
    entries: list[SourceBrowserEntry]
    next_cursor: str | None


class SourceBrowserFile(BaseModel):
    path: str
    status: Literal["ready", "too_large", "binary", "unsupported_encoding", "unavailable"]
    content: str | None = None


class SourceBrowserObject(BaseModel):
    storage_key: str
    size_bytes: int


class SourceBrowserRepository(Protocol):
    async def latest_snapshot(self, source_id: int) -> SourceBrowserSnapshot | None: ...

    async def has_branch(self, source_id: int, snapshot_id: int, branch: str) -> bool: ...

    async def list_entries(
        self, snapshot_id: int, branch: str, folder: str, offset: int, limit: int
    ) -> list[SourceBrowserEntry]: ...

    async def get_file(
        self, source_id: int, snapshot_id: int, branch: str, path: str
    ) -> SourceBrowserObject | None: ...
