from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderUnavailableError(RuntimeError):
    pass


class ModelProviderAdapter(Protocol):
    def list_models(
        self, connection: "ProviderCredentials", timeout: int
    ) -> list["ProviderModel"]: ...

    def pull_model(
        self, connection: "ProviderCredentials", model_id: str, timeout: int
    ) -> Iterator[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ModelProviderDefinition:
    adapter: ModelProviderAdapter
    default_url: str
    display_name: str
    requires_api_key: bool
    fixed_url: bool = False
    sync_all_models: bool = True
    supports_model_pull: bool = False


@dataclass(slots=True)
class ProviderConnection:
    id: int
    provider_type: str
    name: str
    base_url: str
    has_api_key: bool


@dataclass(slots=True)
class ProviderCredentials:
    id: int
    provider_type: str
    name: str
    base_url: str
    api_key: str | None


@dataclass(slots=True)
class ProviderModel:
    provider_model_id: str
    display_name: str
    capabilities: list[str] = field(default_factory=list)
    status: str = "available"
    progress: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkspaceModelEntry(ProviderModel):
    id: int = 0
    provider_connection_id: int = 0
    provider_type: str = ""
    provider_name: str = ""


@dataclass(slots=True)
class ProjectModelSelection:
    source_id: int
    role: str
    model_id: int | None
