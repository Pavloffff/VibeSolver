from hashlib import sha256
from typing import Any
from uuid import uuid4

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

    async def import_documentation(
        self,
        source_id: int,
        files: dict[str, bytes],
        content_types: dict[str, str],
        category: str = "documentation",
        origin: str = "uploaded",
    ) -> dict[str, Any]:
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        resources = source.config.get("resources", {})
        entries = resources.get(category, []) if isinstance(resources, dict) else []
        if not isinstance(entries, list):
            entries = []
        existing_by_path = {
            str(item.get("path", item.get("name", ""))): item
            for item in entries
            if isinstance(item, dict)
        }
        conflicts: list[dict[str, str]] = []
        additions: list[tuple[str, bytes, str]] = []
        for path, data in files.items():
            if path.casefold().endswith(".md"):
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"Markdown file must use UTF-8 encoding: {path}") from exc
            previous = existing_by_path.get(path)
            if previous is None:
                additions.append((path, data, content_types.get(path, "application/octet-stream")))
                continue
            key = self._upload_key(previous)
            body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"]
            previous_data = body if isinstance(body, bytes) else body.read()
            if sha256(previous_data).digest() != sha256(data).digest():
                conflicts.append({"path": path, "existing_id": str(previous.get("id", ""))})
        if conflicts:
            return {"added": [], "unchanged": [], "conflicts": conflicts}
        updated_entries = list(entries)
        added: list[str] = []
        unchanged: list[str] = [path for path in files if path in existing_by_path]
        for path, data, content_type in additions:
            filename = path.rsplit("/", 1)[-1]
            kind = "markdown" if filename.casefold().endswith(".md") else "file"
            try:
                data.decode("utf-8")
                is_text = b"\x00" not in data
            except UnicodeDecodeError:
                is_text = False
            key = f"uploads/{uuid4().hex}"
            self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)
            updated_entries.append({
                "id": uuid4().hex,
                "type": kind,
                "name": filename,
                "path": path,
                "config": {"upload_key": key, "origin": origin, "content_type": content_type, "text": is_text},
            })
            added.append(path)
        if additions:
            updated_config = dict(source.config)
            updated_resources = dict(resources) if isinstance(resources, dict) else {}
            updated_resources[category] = updated_entries
            updated_config["resources"] = updated_resources
            await self._sources.update(source_id, source.name, updated_config)
        return {"added": added, "unchanged": unchanged, "conflicts": []}

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
        if resource is None or resource.get("type") not in {"archive", "markdown", "file"}:
            raise ProjectResourceNotFoundError(resource_id)
        key = self._upload_key(resource)
        self._s3.delete_object(Bucket=self._bucket, Key=key)
        updated_config = dict(source.config)
        updated_resources = dict(resources)
        updated_resources[category] = [item for item in category_resources if item is not resource]
        updated_config["resources"] = updated_resources
        await self._sources.update(source_id, source.name, updated_config)

    async def delete_documentation_folder(
        self, source_id: int, path: str, category: str = "documentation"
    ) -> None:
        source = await self._sources.get_any(source_id)
        if source is None:
            raise SourceNotFoundError(f"project not found: {source_id}")
        resources = source.config.get("resources", {})
        entries = resources.get(category, []) if isinstance(resources, dict) else []
        if not isinstance(entries, list):
            raise ProjectResourceNotFoundError(path)
        descendants = [
            item
            for item in entries
            if isinstance(item, dict)
            and isinstance(item.get("path", item.get("name")), str)
            and str(item.get("path", item.get("name"))).startswith(f"{path}/")
        ]
        if not descendants:
            raise ProjectResourceNotFoundError(path)
        for item in descendants:
            self._s3.delete_object(Bucket=self._bucket, Key=self._upload_key(item))
        updated_config = dict(source.config)
        updated_resources = dict(resources)
        removed_ids = {item.get("id") for item in descendants}
        updated_resources[category] = [
            item for item in entries if not isinstance(item, dict) or item.get("id") not in removed_ids
        ]
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
            if not ProjectResourceUsecase._is_editable_text(item):
                raise ProjectResourceNotFoundError(resource_id)
            return source, item
        raise ProjectResourceNotFoundError(resource_id)

    @staticmethod
    def _is_editable_text(resource: dict[str, Any]) -> bool:
        if resource.get("type") == "markdown":
            return True
        if resource.get("type") != "file":
            return False
        config = resource.get("config", {})
        content_type = config.get("content_type", "") if isinstance(config, dict) else ""
        text_flag = config.get("text") if isinstance(config, dict) else None
        name = resource.get("name", "")
        extensionless = isinstance(name, str) and "." not in name.rsplit("/", 1)[-1]
        return text_flag is True or extensionless or (isinstance(content_type, str) and (
            content_type.startswith("text/")
            or any(kind in content_type for kind in ("json", "xml", "yaml", "javascript"))
        ))

    @staticmethod
    def _upload_key(resource: dict[str, Any]) -> str:
        config = resource.get("config", {})
        key = config.get("upload_key") if isinstance(config, dict) else None
        if not isinstance(key, str) or not key.startswith("uploads/"):
            raise ProjectResourceNotFoundError(str(resource.get("id", "")))
        return key
