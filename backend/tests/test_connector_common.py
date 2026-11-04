import pytest

from app.adapter.connectors import exclusions

EXPECTED_BINARY_EXTENSIONS = {
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
}

EXPECTED_EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
}


def test_binary_extensions_contract() -> None:
    assert isinstance(exclusions.BINARY_EXTENSIONS, frozenset)
    assert EXPECTED_BINARY_EXTENSIONS <= exclusions.BINARY_EXTENSIONS


def test_excluded_dirs_contract() -> None:
    assert isinstance(exclusions.EXCLUDED_DIRS, frozenset)
    assert EXPECTED_EXCLUDED_DIRS <= exclusions.EXCLUDED_DIRS


@pytest.mark.parametrize(
    "rel_path",
    ["photo.png", "app.exe", "lib/core.dll", "static/font.woff2"],
)
def test_is_excluded_binary_extension(rel_path: str) -> None:
    assert exclusions.is_excluded(rel_path) is True


@pytest.mark.parametrize(
    "rel_path",
    [
        "node_modules/pkg.js",
        "src/__pycache__/main.cpython-312.pyc",
        ".venv/lib/site.py",
        "dist/bundle.js",
        ".git/config",
    ],
)
def test_is_excluded_dir_component(rel_path: str) -> None:
    assert exclusions.is_excluded(rel_path) is True


@pytest.mark.parametrize(
    "rel_path",
    ["ignored.log", "logs/ignored.log", "docs/ignored.log"],
)
def test_is_excluded_gitignore_name_pattern(rel_path: str) -> None:
    assert exclusions.is_excluded(rel_path, gitignore_patterns=["ignored.log"]) is True


@pytest.mark.parametrize(
    "rel_path",
    ["src/main.py", "docs/guide.md", "a.txt"],
)
def test_is_excluded_normal_file(rel_path: str) -> None:
    assert exclusions.is_excluded(rel_path) is False


def test_is_excluded_size_over_limit() -> None:
    assert exclusions.is_excluded("big.txt", size=2_000_000, max_file_size=1_000_000)


def test_is_excluded_size_within_limit() -> None:
    assert not exclusions.is_excluded(
        "big.txt",
        size=500_000,
        max_file_size=1_000_000,
        gitignore_patterns=["ignored.log"],
    )


def test_default_max_file_size_excludes_oversized() -> None:
    assert isinstance(exclusions.DEFAULT_MAX_FILE_SIZE, int)
    assert exclusions.DEFAULT_MAX_FILE_SIZE < 5 * 1024 * 1024
    assert exclusions.is_excluded(
        "large.txt",
        size=5 * 1024 * 1024,
        max_file_size=exclusions.DEFAULT_MAX_FILE_SIZE,
    )
