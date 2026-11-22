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

SOLVER_MODEL_ROLES = frozenset(SolverModels.model_fields)


class SolverSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _prepare(self, source_id: int) -> None:
        source = await self._session.execute(
            text("SELECT id FROM sources WHERE id = :source_id FOR UPDATE"),
            {"source_id": source_id},
        )
        if source.scalar_one_or_none() is None:
            raise SourceNotFoundError(f"Project not found: {source_id}")
        await self._session.execute(
            text(
                "INSERT INTO solver_profiles (source_id, name, is_default) "
                "SELECT :source_id, 'Default', TRUE WHERE NOT EXISTS "
                "(SELECT 1 FROM solver_profiles WHERE source_id = :source_id)"
            ),
            {"source_id": source_id},
        )

    async def _rows(self, source_id: int) -> list[RowMapping]:
        result = await self._session.execute(
            text("SELECT * FROM solver_profiles WHERE source_id = :source_id ORDER BY id"),
            {"source_id": source_id},
        )
        return list(result.mappings().all())

    async def list(self, source_id: int) -> tuple[list[SolverProfile], int]:
        await self._prepare(source_id)
        rows = await self._rows(source_id)
        await self._session.commit()
        return [_profile(row) for row in rows], int(
            next(row["id"] for row in rows if row["is_default"])
        )

    async def get(self, source_id: int, profile_id: int | None) -> SolverProfile:
        await self._prepare(source_id)
        for row in await self._rows(source_id):
            matches = row["is_default"] if profile_id is None else row["id"] == profile_id
            if matches:
                return _profile(row)
        raise SolverProfileNotFoundError("Solver profile not found in this project")

    async def set_default_model(self, source_id: int, role: str, model_id: int | None) -> None:
        if role not in SOLVER_MODEL_ROLES:
            raise SolverProfileConflictError("Unknown Solver model role")
        await self._prepare(source_id)
        await self._session.execute(
            text(
                f"UPDATE solver_profiles SET {role} = :model_id WHERE source_id = :source_id AND is_default"
            ),
            {"source_id": source_id, "model_id": model_id},
        )
        await self._session.commit()

    async def save(
        self, source_id: int, profile_id: int | None, profile: SolverProfileInput
    ) -> SolverProfile:
        await self._prepare(source_id)
        rows = await self._rows(source_id)
        if profile_id is not None:
            _find_profile(rows, profile_id)
        if any(row["name"] == profile.name and row["id"] != profile_id for row in rows):
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
                "ticket_resolution, ticket_triage, ticket_resolution_cheap) VALUES "
                "(:source_id, :name, :triage, :resolve, :ticket_resolution, :ticket_triage, "
                ":ticket_resolution_cheap) RETURNING *"
            )
        else:
            statement = (
                "UPDATE solver_profiles SET name = :name, triage_enabled = :triage, "
                "resolve_enabled = :resolve, ticket_resolution = :ticket_resolution, "
                "ticket_triage = :ticket_triage, ticket_resolution_cheap = :ticket_resolution_cheap "
                "WHERE source_id = :source_id AND id = :profile_id RETURNING *"
            )
        result = await self._session.execute(
            text(statement),
            {
                "source_id": source_id,
                "profile_id": profile_id,
                "name": profile.name,
                **profile.enabled.model_dump(),
                **assignments,
            },
        )
        saved = _profile(result.mappings().one())
        await self._session.commit()
        return saved

    async def set_default(self, source_id: int, profile_id: int) -> None:
        await self._prepare(source_id)
        _find_profile(await self._rows(source_id), profile_id)
        await self._set_default(source_id, profile_id)
        await self._session.commit()

    async def _set_default(self, source_id: int, profile_id: int) -> None:
        await self._session.execute(
            text(
                "UPDATE solver_profiles SET is_default = FALSE WHERE source_id = :source_id AND is_default"
            ),
            {"source_id": source_id},
        )
        await self._session.execute(
            text(
                "UPDATE solver_profiles SET is_default = TRUE WHERE source_id = :source_id AND id = :profile_id"
            ),
            {"source_id": source_id, "profile_id": profile_id},
        )

    async def delete(self, source_id: int, profile_id: int, replacement_id: int | None) -> None:
        await self._prepare(source_id)
        rows = await self._rows(source_id)
        if _find_profile(rows, profile_id)["is_default"]:
            if replacement_id is None or replacement_id == profile_id:
                raise SolverProfileConflictError(
                    "Select another profile as the default before deleting"
                )
            _find_profile(rows, replacement_id)
            await self._set_default(source_id, replacement_id)
        await self._session.execute(
            text("DELETE FROM solver_profiles WHERE source_id = :source_id AND id = :profile_id"),
            {"source_id": source_id, "profile_id": profile_id},
        )
        await self._session.commit()


def _find_profile(rows: list[RowMapping], profile_id: int) -> RowMapping:
    for row in rows:
        if row["id"] == profile_id:
            return row
    raise SolverProfileNotFoundError("Solver profile not found in this project")


def _profile(row: RowMapping) -> SolverProfile:
    return SolverProfile(
        id=row["id"],
        name=row["name"],
        enabled=SolverEnabled(triage=row["triage_enabled"], resolve=row["resolve_enabled"]),
        models=SolverModels(
            ticket_resolution=row["ticket_resolution"],
            ticket_triage=row["ticket_triage"],
            ticket_resolution_cheap=row["ticket_resolution_cheap"],
        ),
    )
