from __future__ import annotations

from typing import Any

import pytest

from app.domain.models import Source
from app.usecase.project_resources import ProjectResourceNotFoundError, ProjectResourceUsecase


class FakeSources:
    def __init__(self, source: Source) -> None:
        self.source = source
        self.updated_config: dict[str, Any] | None = None

    async def get_any(self, source_id: int) -> Source | None:
        return self.source if source_id == self.source.id else None

    async def update(self, source_id: int, name: str, config: dict[str, Any]) -> Source:
        self.updated_config = config
        self.source.config = config
        return self.source


class FakeS3:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.deleted.append(Key)
        return {}


def resource(resource_id: str, path: str) -> dict[str, Any]:
    return {"id": resource_id, "type": "file", "name": path.rsplit("/", 1)[-1], "path": path, "config": {"upload_key": f"uploads/{resource_id}"}}


@pytest.mark.asyncio
async def test_delete_documentation_folder_removes_all_descendants() -> None:
    entries = [resource("a", "guide/README.md"), resource("b", "guide/setup/linux.md"), resource("c", "other/keep.md")]
    source = Source(id=1, type="git", name="project", config={"resources": {"documentation": entries}}, enabled=True)
    sources = FakeSources(source)
    s3 = FakeS3()
    usecase = ProjectResourceUsecase(sources, s3, "raw")  # type: ignore[arg-type]

    await usecase.delete_documentation_folder(1, "guide")

    assert s3.deleted == ["uploads/a", "uploads/b"]
    assert [item["id"] for item in sources.updated_config["resources"]["documentation"]] == ["c"]


@pytest.mark.asyncio
async def test_delete_missing_documentation_folder_raises() -> None:
    source = Source(id=1, type="git", name="project", config={"resources": {"documentation": []}}, enabled=True)
    usecase = ProjectResourceUsecase(FakeSources(source), FakeS3(), "raw")  # type: ignore[arg-type]

    with pytest.raises(ProjectResourceNotFoundError):
        await usecase.delete_documentation_folder(1, "missing")
