import json

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import SourceNotFoundError
from app.domain.solver import (
    SolverEnabled,
    SolverModels,
    SolverProfile,
    SolverProfileConflictError,
    SolverProfileInput,
    SolverProfileNotFoundError,
)


class SolverSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_project(self, source_id: int, *, lock: bool = False) -> None:
        statement = "SELECT id FROM sources WHERE id = :source_id"
        if lock:
            statement += " FOR UPDATE"
        result = await self._session.execute(text(statement), {"source_id": source_id})
        if result.scalar_one_or_none() is None:
            raise SourceNotFoundError(f"Project not found: {source_id}")

    async def list(self, source_id: int) -> list[SolverProfile]:
        await self._require_project(source_id)
        result = await self._session.execute(
            text(
                "SELECT * FROM solver_profiles WHERE source_id = :source_id "
                "AND NOT is_archived_seed ORDER BY id"
            ),
            {"source_id": source_id},
        )
        return [_profile(row) for row in result.mappings()]

    async def get(self, source_id: int, profile_id: int) -> SolverProfile:
        result = await self._session.execute(
            text(
                "SELECT * FROM solver_profiles WHERE source_id = :source_id AND id = :profile_id "
                "AND NOT is_archived_seed"
            ),
            {"source_id": source_id, "profile_id": profile_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise SolverProfileNotFoundError("Solver profile not found in this project")
        return _profile(row)

    async def save(
        self, source_id: int, profile_id: int | None, profile: SolverProfileInput
    ) -> SolverProfile:
        await self._require_project(source_id, lock=True)
        if profile_id is not None:
            await self.get(source_id, profile_id)
        existing = await self._session.execute(
            text(
                "SELECT id, is_archived_seed FROM solver_profiles "
                "WHERE source_id = :source_id AND name = :name"
            ),
            {"source_id": source_id, "name": profile.name},
        )
        same_name = existing.mappings().one_or_none()
        if (
            same_name is not None
            and same_name["id"] != profile_id
            and not same_name["is_archived_seed"]
        ):
            raise SolverProfileConflictError("A Solver profile with this name already exists")
        assignments = profile.models.model_dump()
        for model_id in set(assignments.values()) - {None}:
            result = await self._session.execute(
                text(
                    "SELECT id FROM workspace_models WHERE id = :id "
                    "AND capabilities ? 'chat' AND status IN ('available', 'installed') "
                    "FOR SHARE"
                ),
                {"id": model_id},
            )
            if result.scalar_one_or_none() is None:
                raise SolverProfileConflictError("Select an available chat model")
        if profile_id is None:
            statement = (
                "INSERT INTO solver_profiles (source_id, name, triage_enabled, resolve_enabled, "
                "ticket_resolution, ticket_triage, ticket_resolution_cheap, specialist_flags) VALUES "
                "(:source_id, :name, :triage, :resolve, :ticket_resolution, :ticket_triage, "
                ":ticket_resolution_cheap, CAST(:flags AS jsonb)) "
                "ON CONFLICT (source_id, name) DO UPDATE SET is_archived_seed = FALSE, "
                "triage_enabled = EXCLUDED.triage_enabled, resolve_enabled = EXCLUDED.resolve_enabled, "
                "ticket_resolution = EXCLUDED.ticket_resolution, ticket_triage = EXCLUDED.ticket_triage, "
                "ticket_resolution_cheap = EXCLUDED.ticket_resolution_cheap, "
                "specialist_flags = EXCLUDED.specialist_flags "
                "WHERE solver_profiles.is_archived_seed RETURNING *"
            )
        else:
            statement = (
                "UPDATE solver_profiles SET name = :name, triage_enabled = :triage, "
                "resolve_enabled = :resolve, ticket_resolution = :ticket_resolution, "
                "ticket_triage = :ticket_triage, ticket_resolution_cheap = :ticket_resolution_cheap, "
                "specialist_flags = CAST(:flags AS jsonb) "
                "WHERE source_id = :source_id AND id = :profile_id RETURNING *"
            )
        if profile_id is not None and same_name is not None and same_name["is_archived_seed"]:
            await self._session.execute(
                text("DELETE FROM solver_profiles WHERE id = :profile_id AND is_archived_seed"),
                {"profile_id": same_name["id"]},
            )
        result = await self._session.execute(
            text(statement),
            {
                "source_id": source_id,
                "profile_id": profile_id,
                "name": profile.name,
                "triage": profile.enabled.triage,
                "resolve": profile.enabled.resolve,
                "flags": json.dumps(profile.enabled.model_dump(exclude={"triage", "resolve"})),
                **assignments,
            },
        )
        saved = _profile(result.mappings().one())
        await self._session.commit()
        return saved

    async def delete(self, source_id: int, profile_id: int) -> None:
        await self._require_project(source_id, lock=True)
        result = await self._session.execute(
            text(
                "DELETE FROM solver_profiles WHERE source_id = :source_id AND id = :profile_id "
                "AND NOT is_archived_seed RETURNING id"
            ),
            {"source_id": source_id, "profile_id": profile_id},
        )
        if result.scalar_one_or_none() is None:
            raise SolverProfileNotFoundError("Solver profile not found in this project")
        await self._session.commit()


def _profile(row: RowMapping) -> SolverProfile:
    return SolverProfile(
        id=row["id"],
        name=row["name"],
        enabled=SolverEnabled(
            triage=row["triage_enabled"], resolve=row["resolve_enabled"], **row["specialist_flags"]
        ),
        models=SolverModels(
            ticket_resolution=row["ticket_resolution"],
            ticket_triage=row["ticket_triage"],
            ticket_resolution_cheap=row["ticket_resolution_cheap"],
        ),
    )
