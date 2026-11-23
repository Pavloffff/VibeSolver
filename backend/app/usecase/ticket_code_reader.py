from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace

from app.domain.repositories.retrieval import SearchHit
from app.domain.source_browser import SourceBrowserFile
from app.usecase.source_browser import SourceBrowserNotFoundError, SourceBrowserRequestError
from app.usecase.ticket_logs import redact_sensitive_values


class TicketCodeReader:
    def __init__(
        self,
        snapshot_for_run: Callable[[int, int], Awaitable[int | None]],
        read_file: Callable[[int, int, str, str], Awaitable[SourceBrowserFile]],
        surrounding_lines: int,
    ) -> None:
        self._snapshot_for_run = snapshot_for_run
        self._read_file = read_file
        self._surrounding_lines = surrounding_lines

    async def neighbors(self, source_id: int, hit: SearchHit, max_chars: int) -> list[SearchHit]:
        start, end = hit.start_line, hit.end_line
        if hit.index_type != "code" or start is None or end is None or not 1 <= start <= end:
            return []
        snapshot = await self._snapshot_for_run(source_id, hit.run_id)
        if snapshot is None:
            return []
        try:
            preview = await self._read_file(source_id, snapshot, hit.branch, hit.path)
        except (SourceBrowserRequestError, SourceBrowserNotFoundError):
            return []
        if preview.status != "ready" or not preview.content:
            return []
        lines = preview.content.splitlines()
        indexed_text = "\n".join(hit.content.splitlines()).strip()
        if (
            end > len(lines)
            or not indexed_text
            or indexed_text not in "\n".join(lines[start - 1 : end])
        ):
            return []
        windows = (
            range(start - 2, max(-1, start - 2 - self._surrounding_lines), -1),
            range(end, min(len(lines), end + self._surrounding_lines)),
        )
        result = []
        for window in windows:
            neighbor = _bounded_excerpt(hit, lines, window, max_chars // 2)
            if neighbor is not None:
                result.append(neighbor)
        return result


def _bounded_excerpt(
    hit: SearchHit, lines: list[str], window: Iterable[int], budget: int
) -> SearchHit | None:
    selected: list[tuple[int, str]] = []
    for index in window:
        line = redact_sensitive_values(lines[index])
        if len(line) + 1 > budget:
            break
        selected.append((index, line))
        budget -= len(line) + 1
    if not selected:
        return None
    selected.sort()
    content = "\n".join(line for _, line in selected)
    if not content.strip():
        return None
    return replace(
        hit,
        start_line=selected[0][0] + 1,
        end_line=selected[-1][0] + 1,
        content=content,
        symbol=None,
    )
