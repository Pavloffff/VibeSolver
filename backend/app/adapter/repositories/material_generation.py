from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.material_generation import RetrievedChunk


class IndexSearchSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_dense(
        self, source_id: int, index_type: str, run_id: int, vector: list[float], limit: int
    ) -> list[RetrievedChunk]:
        rows = await self._session.execute(
            text(
                "SELECT chunk.id, chunk.path, chunk.branch, chunk.start_line, chunk.end_line, "
                "chunk.symbol, chunk.content, chunk.metadata_json, "
                "1 - (chunk.embedding <=> CAST(:embedding AS vector)) AS score "
                "FROM project_indexes AS project_index "
                "JOIN index_runs AS run ON run.id = project_index.active_run_id "
                "JOIN index_chunks AS chunk ON chunk.run_id = run.id "
                "WHERE project_index.source_id = :source_id "
                "AND project_index.index_type = :index_type AND run.id = :run_id "
                "AND chunk.embedding IS NOT NULL "
                "ORDER BY chunk.embedding <=> CAST(:embedding AS vector) "
                "LIMIT :limit"
            ),
            {
                "source_id": source_id,
                "index_type": index_type,
                "run_id": run_id,
                "embedding": _vector_literal(vector),
                "limit": limit,
            },
        )
        return [_to_chunk(row, index_type) for row in rows.all()]

    async def search_lexical(
        self, source_id: int, index_type: str, run_id: int, query: str, limit: int
    ) -> list[RetrievedChunk]:
        rows = await self._session.execute(
            text(
                "SELECT chunk.id, chunk.path, chunk.branch, chunk.start_line, chunk.end_line, "
                "chunk.symbol, chunk.content, chunk.metadata_json, "
                "ts_rank(chunk.search_vector, plainto_tsquery('simple', :query)) AS score "
                "FROM project_indexes AS project_index "
                "JOIN index_runs AS run ON run.id = project_index.active_run_id "
                "JOIN index_chunks AS chunk ON chunk.run_id = run.id "
                "WHERE project_index.source_id = :source_id "
                "AND project_index.index_type = :index_type AND run.id = :run_id "
                "AND chunk.search_vector @@ plainto_tsquery('simple', :query) "
                "ORDER BY score DESC, chunk.id "
                "LIMIT :limit"
            ),
            {
                "source_id": source_id,
                "index_type": index_type,
                "run_id": run_id,
                "query": query,
                "limit": limit,
            },
        )
        return [_to_chunk(row, index_type) for row in rows.all()]


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def _to_chunk(row: Any, index_type: str) -> RetrievedChunk:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return RetrievedChunk(
        chunk_id=int(row.id),
        index_type=index_type,
        path=str(row.path),
        branch=str(row.branch),
        start_line=int(row.start_line) if row.start_line is not None else None,
        end_line=int(row.end_line) if row.end_line is not None else None,
        symbol=str(row.symbol) if row.symbol is not None else None,
        content=str(row.content),
        metadata=metadata,
        score=float(row.score),
    )
