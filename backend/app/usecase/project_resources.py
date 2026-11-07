from typing import Any

from app.domain.entities import SourceNotFoundError
from app.domain.models import Source
from app.domain.repositories import SourceRepository
from app.domain.storage import S3Like


class ProjectResourceNotFoundError(LookupError):
    pass


class ProjectResourceUsecase:
    def __init__(self, sources: SourceRepository, s3: S3Like, bucket: str) -> None:
        self._sources = sources
        self._s3 = s3
        self._bucket = bucket

    async def read_markdown(self, source_id: int, category: str, resource_id: str) -> str:
        _, resource = await self._find_markdown(source_id, category, resource_id)
        key = self._upload_key(resource)
        result = self._s3.get_object(Bucket=self._bucket, Key=key)
        body = result["Body"]
        data = body if isinstance(body, bytes) else body.read()
        return data.decode("utf-8")

    async def update_markdown(
        self, source_id: int, category: str, resource_id: str, content: str
    ) -> None:
        _, resource = await self._find_markdown(source_id, category, resource_id)
        key = self._upload_key(resource)
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=content.encode("utf-8"))

    async def delete_resource(self, source_id: int, category: str, resource_id: str) -> None:
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        resources = source.config.get("resources", {})
        category_resources = resources.get(category, []) if isinstance(resources, dict) else []
        if not isinstance(category_resources, list):
            raise ProjectResourceNotFoundError(resource_id)
        resource = next(
            (
                item
                for item in category_resources
                if isinstance(item, dict) and item.get("id") == resource_id
            ),
            None,
        )
        if resource is None or resource.get("type") not in {"archive", "markdown"}:
            raise ProjectResourceNotFoundError(resource_id)
        key = self._upload_key(resource)
        self._s3.delete_object(Bucket=self._bucket, Key=key)
        updated_config = dict(source.config)
        updated_resources = dict(resources)
        updated_resources[category] = [item for item in category_resources if item is not resource]
        updated_config["resources"] = updated_resources
        await self._sources.update(source_id, source.name, updated_config)

    async def _find_markdown(
        self, source_id: int, category: str, resource_id: str
    ) -> tuple[Source, dict[str, Any]]:
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        resources = source.config.get("resources", {})
        category_resources = resources.get(category, []) if isinstance(resources, dict) else []
        if not isinstance(category_resources, list):
            raise ProjectResourceNotFoundError(resource_id)
        for item in category_resources:
            if not isinstance(item, dict) or item.get("id") != resource_id:
                continue
            if item.get("type") != "markdown":
                raise ProjectResourceNotFoundError(resource_id)
            return source, item
        raise ProjectResourceNotFoundError(resource_id)

    @staticmethod
    def _upload_key(resource: dict[str, Any]) -> str:
        config = resource.get("config", {})
        key = config.get("upload_key") if isinstance(config, dict) else None
        if not isinstance(key, str) or not key.startswith("uploads/"):
            raise ProjectResourceNotFoundError(str(resource.get("id", "")))
        return key
