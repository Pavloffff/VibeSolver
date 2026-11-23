import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.material_generation import LiteralCodeMatch, RetrievedChunk


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

    async def search_code_literal(
        self, source_id: int, run_id: int, literal: str, limit: int
    ) -> list[LiteralCodeMatch]:
        boundary = "[:alnum:]_./%{}-" if literal.startswith("/") else "[:alnum:]_"
        pattern = f"(^|[^{boundary}])({re.escape(literal)})($|[^{boundary}])"
        rows = await self._session.execute(
            text("""
                SELECT chunk.id, chunk.path, chunk.branch, chunk.start_line, chunk.end_line,
                       chunk.symbol, chunk.content, chunk.metadata_json, 1.0 AS score,
                       regexp_instr(chunk.content, :pattern, 1, 1, 0, '', 2) - 1 AS match_offset
                FROM project_indexes AS project_index
                JOIN index_runs AS run ON run.id = project_index.active_run_id
                    AND run.project_index_id = project_index.id
                JOIN index_chunks AS chunk ON chunk.run_id = run.id
                WHERE project_index.source_id = :source_id
                  AND project_index.index_type = 'code'
                  AND run.id = :run_id AND run.status = 'completed'
                  AND chunk.search_vector @@ plainto_tsquery('simple', :literal)
                  AND strpos(chunk.content, :literal) > 0
                  AND chunk.content ~ :pattern
                ORDER BY CASE WHEN
                        chunk.path ~* '(^|/)(docs?|documentation|specs?|tests?|__tests__|fixtures|examples)(/|$)'
                        OR chunk.path ~* '(^|/)(openapi|swagger)([._-]|$)'
                        OR chunk.path ~* '(_test|Tests|[.]spec|[.]test)[.][^/]+$'
                        OR chunk.path ~* '[.](md|rst|adoc)$'
                    THEN 1 ELSE 0 END, chunk.id
                LIMIT :limit
            """),
            {
                "source_id": source_id,
                "run_id": run_id,
                "literal": literal,
                "pattern": pattern,
                "limit": min(8, max(0, limit)),
            },
        )
        return [LiteralCodeMatch(_to_chunk(row, "code"), int(row.match_offset)) for row in rows]


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
