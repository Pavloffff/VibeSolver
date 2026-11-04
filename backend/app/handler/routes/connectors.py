from fastapi import APIRouter

from app.adapter.connectors import ConnectorCatalogImpl
from app.handler.schemas import ConfigSchema, ConnectorInfo
from app.usecase.connectors_info import ConnectorsInfoUsecase

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorInfo])
async def list_connectors() -> list[ConnectorInfo]:
    usecase = ConnectorsInfoUsecase(ConnectorCatalogImpl())
    return [
        ConnectorInfo(
            type=descriptor.type,
            ready=descriptor.ready,
            config_schema=ConfigSchema(fields=descriptor.config_fields),
        )
        for descriptor in usecase.list_descriptors()
    ]
