from app.domain.entities import ConnectorDescriptor
from app.domain.repositories import ConnectorCatalog


class ConnectorsInfoUsecase:
    def __init__(self, connectors: ConnectorCatalog) -> None:
        self._connectors = connectors

    def list_descriptors(self) -> list[ConnectorDescriptor]:
        return self._connectors.descriptors()
