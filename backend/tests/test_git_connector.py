import hashlib
from pathlib import Path
from typing import Any

import pytest
from dulwich.porcelain import add, commit
from dulwich.repo import Repo

from app.adapter.connectors.git import GitConnector

COMMIT_AUTHOR: bytes = b"Tester <tester" + bytes([64]) + b"example.com>"


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}".encode()
    return hashlib.sha1(header + b"\x00" + content).hexdigest()


def is_hex40(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    return all(char in "0123456789abcdef" for char in value)


def set_head(root: Path, branch: bytes) -> None:
    head_path = root / ".git" / "HEAD"
    head_path.write_bytes(b"ref: refs/heads/" + branch + b"\n")


def make_commit(repo: Repo, message: bytes, branch: bytes) -> bytes:
    set_head(Path(repo.path), branch)
    return commit(
        repo,
        message=message,
        author=COMMIT_AUTHOR,
        author_timestamp=0.0,
        author_timezone=0,
        committer=COMMIT_AUTHOR,
        commit_timestamp=0.0,
        commit_timezone=0,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "repo"
    root.mkdir()
    tracked: dict[str, bytes] = {
        "README.md": b"# readme\n",
        "src/main.py": b"print('hi')\n",
        "binary.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        "docs/guide.md": b"# guide\n",
        ".gitignore": b"ignored.log\n",
    }
    for rel, content in tracked.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    with Repo.init(str(root)) as repo:
        add(repo.path, list(tracked))
        main_commit = make_commit(repo, b"initial", b"main")
        (root / "ignored.log").write_bytes(b"ignored\n")
        repo.refs[b"refs/heads/dev"] = main_commit
        (root / "dev_only.txt").write_bytes(b"dev\n")
        add(repo.path, ["dev_only.txt"])
        dev_commit = make_commit(repo, b"dev work", b"dev")
        set_head(root, b"main")
    return {
        "root": root,
        "tracked": tracked,
        "main_commit": main_commit.decode("ascii"),
        "dev_commit": dev_commit.decode("ascii"),
        "default_branch": "main",
    }


def test_git_fetch_main(git_repo: dict[str, Any]) -> None:
    connector = GitConnector()
    config = {"url": str(git_repo["root"]), "branches": ["main"]}
    items = list(connector.fetch_snapshot(config))
    by_path = {item.path: item for item in items}
    assert set(by_path) == {"README.md", "src/main.py", "docs/guide.md"}
    for rel, expected in git_repo["tracked"].items():
        if rel not in by_path:
            continue
        item = by_path[rel]
        assert "\\" not in item.path
        assert item.content == expected
        assert item.meta["branch"] == "main"
        assert item.meta["blob_sha"] == git_blob_sha(expected)
        assert is_hex40(item.meta["blob_sha"])
        assert item.meta["commit_sha"] == git_repo["main_commit"]
        assert is_hex40(item.meta["commit_sha"])


def test_git_fetch_multiple_branches(git_repo: dict[str, Any]) -> None:
    connector = GitConnector()
    config = {"url": str(git_repo["root"]), "branches": ["main", "dev"]}
    items = list(connector.fetch_snapshot(config))
    by_path_branch = {(item.path, item.meta["branch"]) for item in items}
    expected = {
        ("README.md", "main"),
        ("src/main.py", "main"),
        ("docs/guide.md", "main"),
        ("README.md", "dev"),
        ("src/main.py", "dev"),
        ("docs/guide.md", "dev"),
        ("dev_only.txt", "dev"),
    }
    assert by_path_branch == expected


def test_git_fetch_default_branch(git_repo: dict[str, Any]) -> None:
    connector = GitConnector()
    config = {"url": str(git_repo["root"])}
    items = list(connector.fetch_snapshot(config))
    assert items
    assert {item.path for item in items} == {"README.md", "src/main.py", "docs/guide.md"}
    for item in items:
        assert item.meta["branch"] == git_repo["default_branch"]


def test_git_fetch_cleans_work_dir(git_repo: dict[str, Any], tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    connector = GitConnector()
    config = {"url": str(git_repo["root"]), "branches": ["main"]}
    items = list(connector.fetch_snapshot(config, work_dir=str(work_dir)))
    assert items
    assert not any(work_dir.iterdir())


def test_git_fetch_missing_branch_raises(git_repo: dict[str, Any]) -> None:
    connector = GitConnector()
    config = {"url": str(git_repo["root"]), "branches": ["main", "nonexistent"]}
    with pytest.raises(RuntimeError, match="nonexistent"):
        list(connector.fetch_snapshot(config))
