from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.db import get_session
from app.adapter.repositories.solver import SolverSqlRepository
from app.domain.entities import SourceNotFoundError
from app.domain.solver import (
    SolverProfile,
    SolverProfileConflictError,
    SolverProfileInput,
    SolverProfileNotFoundError,
)
from app.usecase.ticket_agent import SOLVER_OPTIONAL_STAGES, SOLVER_STAGE_IDS, solver_public_edges

router = APIRouter(prefix="/sources", tags=["solver"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class SolverNodeOut(BaseModel):
    id: str
    optional: bool


class SolverEdgeOut(BaseModel):
    source: str
    target: str


class SolverGraphOut(BaseModel):
    nodes: list[SolverNodeOut]
    edges: list[SolverEdgeOut]
    profiles: list[SolverProfile]
    default_profile_id: int


@contextmanager
def profile_errors() -> Iterator[None]:
    try:
        yield
    except (SourceNotFoundError, SolverProfileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SolverProfileConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{source_id}/solver-graph", response_model=SolverGraphOut)
async def get_solver_graph(source_id: int, session: SessionDep) -> SolverGraphOut:
    with profile_errors():
        profiles, default_id = await SolverSqlRepository(session).list(source_id)
        return SolverGraphOut(
            nodes=[
                SolverNodeOut(id=node, optional=node in SOLVER_OPTIONAL_STAGES)
                for node in SOLVER_STAGE_IDS
            ],
            edges=[SolverEdgeOut(source=start, target=end) for start, end in solver_public_edges()],
            profiles=profiles,
            default_profile_id=default_id,
        )


@router.post("/{source_id}/solver-profiles", status_code=201, response_model=SolverProfile)
async def create_solver_profile(
    source_id: int, payload: SolverProfileInput, session: SessionDep
) -> SolverProfile:
    with profile_errors():
        return await SolverSqlRepository(session).save(source_id, None, payload)


@router.put("/{source_id}/solver-profiles/{profile_id}", response_model=SolverProfile)
async def update_solver_profile(
    source_id: int, profile_id: int, payload: SolverProfileInput, session: SessionDep
) -> SolverProfile:
    with profile_errors():
        return await SolverSqlRepository(session).save(source_id, profile_id, payload)


@router.put("/{source_id}/solver-profiles/{profile_id}/default", status_code=204)
async def set_default_solver_profile(
    source_id: int, profile_id: int, session: SessionDep
) -> Response:
    with profile_errors():
        await SolverSqlRepository(session).set_default(source_id, profile_id)
    return Response(status_code=204)


@router.delete("/{source_id}/solver-profiles/{profile_id}", status_code=204)
async def delete_solver_profile(
    source_id: int,
    profile_id: int,
    session: SessionDep,
    replacement_id: Annotated[int | None, Query(gt=0)] = None,
) -> Response:
    with profile_errors():
        await SolverSqlRepository(session).delete(source_id, profile_id, replacement_id)
    return Response(status_code=204)
