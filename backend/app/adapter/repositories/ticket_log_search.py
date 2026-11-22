from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.ticket_log_search import RetrievedTicketLogChunk


class TicketLogSearchSqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_dense(
        self,
        source_id: int,
        ticket_id: int,
        embedding_model_id: int,
        vector: list[float],
        limit: int,
    ) -> list[RetrievedTicketLogChunk]:
        rows = await self._session.execute(
            text(
                "SELECT chunk.id, chunk.attachment_id, chunk.ticket_id, chunk.path, "
                "chunk.start_line, chunk.end_line, chunk.event_timestamp, chunk.content, "
                "chunk.metadata_json, 1 - (chunk.embedding <=> CAST(:embedding AS vector)) "
                "AS score FROM ticket_log_chunks AS chunk "
                "JOIN ticket_log_attachments AS attachment ON attachment.id = chunk.attachment_id "
                "AND attachment.source_id = chunk.source_id AND attachment.ticket_id = chunk.ticket_id "
                "WHERE chunk.source_id = :source_id AND chunk.ticket_id = :ticket_id "
                "AND attachment.status = 'ready' "
                "AND attachment.embedding_model_id = :embedding_model_id "
                "AND chunk.embedding IS NOT NULL "
                "ORDER BY chunk.embedding <=> CAST(:embedding AS vector), chunk.id LIMIT :limit"
            ),
            {
                "source_id": source_id,
                "ticket_id": ticket_id,
                "embedding_model_id": embedding_model_id,
                "embedding": _vector_literal(vector),
                "limit": limit,
            },
        )
        return [_to_log_chunk(row) for row in rows.all()]

    async def search_lexical(
        self, source_id: int, ticket_id: int, query: str, limit: int
    ) -> list[RetrievedTicketLogChunk]:
        rows = await self._session.execute(
            text(
                "SELECT chunk.id, chunk.attachment_id, chunk.ticket_id, chunk.path, "
                "chunk.start_line, chunk.end_line, chunk.event_timestamp, chunk.content, "
                "chunk.metadata_json, ts_rank(chunk.search_vector, "
                "plainto_tsquery('simple', :query)) AS score FROM ticket_log_chunks AS chunk "
                "JOIN ticket_log_attachments AS attachment ON attachment.id = chunk.attachment_id "
                "AND attachment.source_id = chunk.source_id AND attachment.ticket_id = chunk.ticket_id "
                "WHERE chunk.source_id = :source_id AND chunk.ticket_id = :ticket_id "
                "AND attachment.status = 'ready' "
                "AND chunk.search_vector @@ plainto_tsquery('simple', :query) "
                "ORDER BY score DESC, chunk.id LIMIT :limit"
            ),
            {
                "source_id": source_id,
                "ticket_id": ticket_id,
                "query": query,
                "limit": limit,
            },
        )
        return [_to_log_chunk(row) for row in rows.all()]


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def _to_log_chunk(row: Any) -> RetrievedTicketLogChunk:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return RetrievedTicketLogChunk(
        chunk_id=int(row.id),
        attachment_id=int(row.attachment_id),
        ticket_id=int(row.ticket_id),
        path=str(row.path),
        start_line=int(row.start_line),
        end_line=int(row.end_line),
        event_timestamp=(str(row.event_timestamp) if row.event_timestamp is not None else None),
        content=str(row.content),
        metadata=metadata,
        score=float(row.score),
    )
