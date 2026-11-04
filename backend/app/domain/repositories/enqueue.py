from typing import Protocol


class ImportEnqueuer(Protocol):
    def __call__(self, source_id: int) -> str: ...
