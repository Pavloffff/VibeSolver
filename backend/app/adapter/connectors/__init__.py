from app.adapter.connectors.base import BaseConnector
from app.adapter.connectors.git import GitConnector
from app.adapter.connectors.hg import MercurialConnector
from app.adapter.connectors.local_folder import LocalFolderConnector
from app.adapter.connectors.svn import SvnConnector
from app.domain.entities import ConnectorDescriptor
from app.domain.repositories import ConnectorSPI

__all__ = [
    "CONNECTOR_REGISTRY",
    "BaseConnector",
    "ConnectorCatalogImpl",
    "GitConnector",
    "LocalFolderConnector",
    "MercurialConnector",
    "SvnConnector",
]

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    connector.type: connector
    for connector in (
        GitConnector,
        LocalFolderConnector,
        SvnConnector,
        MercurialConnector,
    )
}


class ConnectorCatalogImpl:
    def get(self, source_type: str) -> ConnectorSPI | None:
        connector_class = CONNECTOR_REGISTRY.get(source_type)
        if connector_class is None:
            return None
        return connector_class()

    def descriptors(self) -> list[ConnectorDescriptor]:
        return [
            ConnectorDescriptor(
                type=connector.type,
                ready=connector.ready,
                config_fields=list(connector.config_fields),
            )
            for connector in CONNECTOR_REGISTRY.values()
        ]
