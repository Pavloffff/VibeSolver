from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
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
from app.usecase.ticket_agent import solver_optional_stages, solver_public_edges, solver_stage_ids

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
    default_profile_id: None = None


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
        profiles = await SolverSqlRepository(session).list(source_id)
        optional_stages = solver_optional_stages()
        return SolverGraphOut(
            nodes=[
                SolverNodeOut(id=node, optional=node in optional_stages)
                for node in solver_stage_ids()
            ],
            edges=[SolverEdgeOut(source=start, target=end) for start, end in solver_public_edges()],
            profiles=profiles,
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


@router.put(
    "/{source_id}/solver-profiles/{profile_id}/default",
    status_code=410,
    deprecated=True,
)
async def set_default_solver_profile(source_id: int, profile_id: int) -> None:
    raise HTTPException(
        status_code=410,
        detail="Choose a Solver profile for each run. Projects have no default profile.",
    )


@router.delete("/{source_id}/solver-profiles/{profile_id}", status_code=204)
async def delete_solver_profile(
    source_id: int,
    profile_id: int,
    session: SessionDep,
) -> Response:
    with profile_errors():
        await SolverSqlRepository(session).delete(source_id, profile_id)
    return Response(status_code=204)
