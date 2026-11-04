from fnmatch import fnmatchcase
from pathlib import PurePosixPath

BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".zip",
        ".tar",
        ".gz",
        ".7z",
        ".rar",
        ".pdf",
        ".bin",
        ".woff",
        ".woff2",
        ".ttf",
        ".pyc",
        ".class",
        ".jar",
        ".wav",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
    }
)

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
        ".idea",
        ".vscode",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "coverage",
    }
)

DEFAULT_MAX_FILE_SIZE: int = 4 * 1024 * 1024


def parse_gitignore(text: str) -> list[str]:
    patterns: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns


def is_excluded(
    rel_path: str,
    gitignore_patterns: list[str] | None = None,
    max_file_size: int | None = None,
    size: int | None = None,
) -> bool:
    path = PurePosixPath(rel_path)
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    if any(part in EXCLUDED_DIRS for part in path.parts[:-1]):
        return True
    if gitignore_patterns is not None:
        name = path.name
        for pattern in gitignore_patterns:
            if fnmatchcase(name, pattern):
                return True
    return bool(size is not None and max_file_size is not None and size > max_file_size)
