import hashlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

from app.adapter.connectors.base import BaseConnector
from app.adapter.connectors.exclusions import (
    DEFAULT_MAX_FILE_SIZE,
    EXCLUDED_DIRS,
    is_excluded,
    parse_gitignore,
)
from app.domain.entities import ConfigField, ConfigValidationError, RawItem


class LocalFolderConnector(BaseConnector):
    type: ClassVar[str] = "local_folder"
    ready: ClassVar[bool] = True
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            name="path",
            label="Folder on your computer",
            kind="folder",
            required=True,
            hint="The folder will be imported recursively (binaries and service folders are skipped)",
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        path = config.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ConfigValidationError("local_folder source config requires a non-empty 'path'")

    def fetch_snapshot(
        self, config: dict[str, Any], work_dir: str | None = None
    ) -> Iterator[RawItem]:
        root = Path(str(config.get("path", "")).strip())
        patterns = _root_gitignore_patterns(root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS)
            for filename in sorted(filenames):
                if filename == ".gitignore":
                    continue
                full = Path(dirpath) / filename
                rel = full.relative_to(root).as_posix()
                size = full.stat().st_size
                if is_excluded(rel, patterns, DEFAULT_MAX_FILE_SIZE, size):
                    continue
                content = full.read_bytes()
                yield RawItem(
                    path=rel,
                    content=content,
                    meta={
                        "size": size,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    },
                )


def _root_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return []
    return parse_gitignore(gitignore.read_text(encoding="utf-8", errors="replace"))
