import shutil
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, cast

from dulwich.objects import Blob, Commit, ObjectID, RawObjectID, Tree
from dulwich.porcelain import clone
from dulwich.refs import Ref, RefsContainer
from dulwich.repo import Repo

from app.adapter.connectors.base import BaseConnector
from app.adapter.connectors.exclusions import (
    DEFAULT_MAX_FILE_SIZE,
    is_excluded,
    parse_gitignore,
)
from app.domain.entities import ConfigField, ConfigValidationError, RawItem


class GitConnector(BaseConnector):
    type: ClassVar[str] = "git"
    ready: ClassVar[bool] = True
    config_fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            name="url",
            label="Repository URL",
            kind="text",
            required=True,
            placeholder="https://github.com/owner/repo.git",
        ),
        ConfigField(
            name="token_ref",
            label="Access token (PAT)",
            kind="password",
            required=False,
            hint=(
                "Only for private repositories. GitHub: Settings -> Developer settings -> "
                "Personal access tokens -> Generate new token (scope: repo). GitLab: "
                "Preferences -> Access tokens (scope: read_api, read_repository)."
            ),
        ),
    ]

    def validate_config(self, config: dict[str, Any]) -> None:
        url = config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ConfigValidationError("git source config requires a non-empty 'url'")
        branches = config.get("branches")
        if branches is not None and not _is_branch_list(branches):
            raise ConfigValidationError(
                "'branches' must be a list of branch names or a comma-separated string"
            )
        token_ref = config.get("token_ref")
        if token_ref is not None and not isinstance(token_ref, str):
            raise ConfigValidationError("'token_ref' must be a string")

    def fetch_snapshot(
        self, config: dict[str, Any], work_dir: str | None = None
    ) -> Iterator[RawItem]:
        url = str(config.get("url", "")).strip()
        branches = _normalize_branches(config.get("branches"))
        local_path = _local_repo_path(url)
        if local_path is not None:
            with Repo(str(local_path)) as repo:
                yield from _snapshot_repo(repo, branches)
            return
        if work_dir is not None:
            base = Path(work_dir)
            base.mkdir(parents=True, exist_ok=True)
            yield from _snapshot_remote(url, branches, base)
            return
        with tempfile.TemporaryDirectory() as tmp:
            yield from _snapshot_remote(url, branches, Path(tmp))


def _snapshot_remote(url: str, branches: list[str] | None, base: Path) -> Iterator[RawItem]:
    if branches is None:
        clone_dir = base / "clone"
        clone_dir.mkdir(parents=True, exist_ok=True)
        try:
            yield from _clone_and_snapshot(url, None, clone_dir)
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)
        return
    for index, branch in enumerate(branches):
        clone_dir = base / f"clone-{index}"
        clone_dir.mkdir(parents=True, exist_ok=True)
        try:
            yield from _clone_and_snapshot(url, branch, clone_dir)
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)


def _clone_and_snapshot(
    url: str, branch: str | None, clone_dir: Path
) -> Iterator[RawItem]:
    try:
        if branch is None:
            clone(url, str(clone_dir), depth=1)
        else:
            clone(url, str(clone_dir), depth=1, branch=branch)
    except ValueError as exc:
        raise RuntimeError(f"branch not found: {branch}") from exc
    except Exception as exc:
        raise RuntimeError(f"unknown repo (clone failed): {url}") from exc
    with Repo(str(clone_dir)) as repo:
        yield from _snapshot_repo(repo, [branch] if branch is not None else None)


def _is_branch_list(value: object) -> bool:
    if isinstance(value, str):
        return True
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    return False


def _normalize_branches(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        names = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        names = [str(part).strip() for part in value]
    else:
        names = []
    names = [name for name in names if name]
    return names or None


def _local_repo_path(url: str) -> Path | None:
    if url.startswith(("http://", "https://", "git://", "ssh://")):
        return None
    if "@" in url.split(":")[0]:
        return None
    path = Path(url)
    if path.exists() and (path / ".git").exists():
        return path
    if path.exists() and (path / "HEAD").exists() and path.suffix == ".git":
        return path
    return None


def _default_branch(repo: Repo) -> str:
    head = repo.refs.read_ref(cast("Ref", b"HEAD"))
    if head is not None and head.startswith(b"ref: "):
        ref = head[len(b"ref: ") :].strip()
        prefix = b"refs/heads/"
        if ref.startswith(prefix):
            return ref[len(prefix) :].decode("utf-8")
    return "HEAD"


def _read_sha(refs: RefsContainer, ref: bytes) -> bytes | None:
    value = refs.read_ref(cast("Ref", ref))
    if value is None:
        return None
    if value.startswith(b"ref: "):
        return _read_sha(refs, value[len(b"ref: ") :].strip())
    return value


def _hex_sha(sha: bytes) -> str:
    if len(sha) == 20:
        return sha.hex()
    return sha.decode("ascii")


def _branch_commit(repo: Repo, branch: str) -> bytes | None:
    if branch == "HEAD":
        return _read_sha(repo.refs, b"HEAD")
    sha = _read_sha(repo.refs, b"refs/heads/" + branch.encode("utf-8"))
    if sha is not None:
        return sha
    return _read_sha(repo.refs, branch.encode("utf-8"))


def _collect_files(
    repo: Repo, tree_sha: ObjectID | RawObjectID, prefix: str
) -> list[tuple[str, bytes, str]]:
    files: list[tuple[str, bytes, str]] = []
    tree = cast("Tree", repo.object_store[tree_sha])
    for entry in tree.items():
        name = entry.path.decode("utf-8", errors="replace")
        rel = prefix + name
        if stat.S_ISDIR(entry.mode):
            files.extend(_collect_files(repo, cast("RawObjectID", entry.sha), rel + "/"))
        else:
            blob = cast("Blob", repo.object_store[entry.sha])
            files.append((rel, blob.data, blob.id.decode("ascii")))
    return files


def _gitignore_patterns(repo: Repo, tree_sha: ObjectID | RawObjectID) -> list[str]:
    tree = cast("Tree", repo.object_store[tree_sha])
    for entry in tree.items():
        if entry.path == b".gitignore":
            blob = cast("Blob", repo.object_store[cast("RawObjectID", entry.sha)])
            return parse_gitignore(blob.data.decode("utf-8", errors="replace"))
    return []


def _snapshot_repo(repo: Repo, branches: list[str] | None) -> Iterator[RawItem]:
    if branches is None:
        branches = [_default_branch(repo)]
    for branch in branches:
        commit_sha = _branch_commit(repo, branch)
        if commit_sha is None:
            raise RuntimeError(f"branch not found: {branch}")
        commit = cast("Commit", repo.object_store[cast("RawObjectID", commit_sha)])
        tree_sha = commit.tree
        patterns = _gitignore_patterns(repo, tree_sha)
        for rel, content, blob_sha in _collect_files(repo, tree_sha, ""):
            if PurePosixPath(rel).name == ".gitignore":
                continue
            if is_excluded(rel, patterns, DEFAULT_MAX_FILE_SIZE, len(content)):
                continue
            yield RawItem(
                path=rel,
                content=content,
                meta={
                    "branch": branch,
                    "blob_sha": blob_sha,
                    "commit_sha": _hex_sha(commit_sha),
                },
            )
