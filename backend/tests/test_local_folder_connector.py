import hashlib
from pathlib import Path
from typing import Any

import pytest

from app.adapter.connectors.local_folder import LocalFolderConnector

LARGE_FILE_SIZE = 5 * 1024 * 1024


@pytest.fixture
def source_folder(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "folder"
    root.mkdir()
    files: dict[str, bytes] = {
        "a.txt": b"alpha\n",
        "src/b.py": b"print(1)\n",
        "img.bin": b"\x89PNG" + b"\x00" * 32,
        "node_modules/pkg.js": b"module.exports = 1\n",
        ".git/config": b"[core]\n",
        ".gitignore": b"ignored.log\n",
        "ignored.log": b"log line\n",
        "large.txt": b"a" * LARGE_FILE_SIZE,
    }
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return {"root": root, "files": files}


def test_local_folder_fetch(source_folder: dict[str, Any]) -> None:
    connector = LocalFolderConnector()
    items = list(connector.fetch_snapshot({"path": str(source_folder["root"])}))
    by_path = {item.path: item for item in items}
    assert set(by_path) == {"a.txt", "src/b.py"}
    for rel in ("a.txt", "src/b.py"):
        expected: bytes = source_folder["files"][rel]
        item = by_path[rel]
        assert "\\" not in item.path
        assert item.content == expected
        assert item.meta["size"] == len(expected)
        assert item.meta["sha256"] == hashlib.sha256(expected).hexdigest()
