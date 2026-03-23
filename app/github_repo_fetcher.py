from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import json
import requests as _requests

from github import Github
from github.GithubException import GithubException


_GITHUB_REPO_URL_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)"
    r"(?:\.git)?/?$"
)


class RepoFetchError(Exception):
    pass


class RepoNotFoundError(RepoFetchError):
    pass


class RepoUnauthorizedError(RepoFetchError):
    pass


class RepoEmptyError(RepoFetchError):
    pass


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str


@dataclass(frozen=True)
class RepoMetadata:
    """Structured metadata from the GitHub repo and languages API endpoints."""
    description: Optional[str]
    topics: List[str]
    # language -> bytes of code, e.g. {"Ruby": 18167777, "JavaScript": 234570}
    languages: Dict[str, int]
    default_branch: str
    homepage: Optional[str]
    stars: int


@dataclass(frozen=True)
class KeyFileContent:
    name: str
    content: str


@dataclass
class RepoContext:
    metadata: RepoMetadata
    # Filtered, sorted file paths from the recursive tree
    paths: List[str] = field(default_factory=list)
    key_files_content: List[KeyFileContent] = field(default_factory=list)
    # Fields needed for tool-based file access
    owner: str = ""
    repo_name: str = ""
    commit_sha: str = ""


def parse_github_repo_url(github_url: str) -> RepoRef:
    match = _GITHUB_REPO_URL_RE.match(github_url.strip())
    if not match:
        raise ValueError("Invalid github_url. Expected public GitHub repo URL.")
    return RepoRef(owner=match.group("owner"), repo=match.group("repo"))


# These are "unsafe for LLM context" heuristics: binaries, build artifacts, vendor deps, etc.
_FILTER_CONFIG_PATH = Path(__file__).resolve().parent / "repo_filter_config.json"

_FILTER_CONFIG = json.loads(_FILTER_CONFIG_PATH.read_text(encoding="utf-8"))

_EXCLUDED_DIR_PREFIXES: Sequence[str] = tuple(
    _FILTER_CONFIG["excluded_dir_prefixes"]
)
_EXCLUDED_FILE_EXTENSIONS: Sequence[str] = tuple(
    _FILTER_CONFIG["excluded_file_extensions"]
)
_EXCLUDED_LOCK_FILENAMES = set(_FILTER_CONFIG["excluded_lock_filenames"])
_KEY_FILES: List[str] = _FILTER_CONFIG.get("key_files", [])
_MAX_KEY_FILE_CHARS = 12_000


def _is_excluded_path(path: str) -> bool:
    # Normalize separators for GitHub tree paths (always forward slashes).
    norm = path.strip("/")
    if not norm:
        return True

    for prefix in _EXCLUDED_DIR_PREFIXES:
        if norm.startswith(prefix):
            return True

    filename = norm.split("/")[-1]
    if filename in _EXCLUDED_LOCK_FILENAMES:
        return True

    lower = norm.lower()
    for ext in _EXCLUDED_FILE_EXTENSIONS:
        if lower.endswith(ext):
            return True

    return False



_MAX_FILE_CONTENT_CHARS = 8_000


def ls_directory(paths: List[str], directory: str) -> List[str]:
    """Return immediate children (files and subdirs) of *directory* from the flat path list."""
    prefix = directory.rstrip("/") + "/" if directory.strip("/") else ""
    entries: set[str] = set()
    for path in paths:
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix):]
        if not rest:
            continue
        slash = rest.find("/")
        if slash == -1:
            entries.add(prefix + rest)
        else:
            entries.add(prefix + rest[:slash] + "/")
    return sorted(entries)


def fetch_file_content(owner: str, repo_name: str, commit_sha: str, path: str) -> str:
    """Fetch raw file content from GitHub. Returns text or an error string."""
    if not owner or not repo_name or not commit_sha:
        return "Error: repo context not fully initialised (missing owner/repo/sha)."
    url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{commit_sha}/{path}"
    try:
        resp = _requests.get(url, timeout=15)
    except _requests.RequestException as exc:
        return f"Error fetching '{path}': {exc}"
    if resp.status_code == 404:
        return f"Error: '{path}' not found in repository."
    if not resp.ok:
        return f"Error: HTTP {resp.status_code} fetching '{path}'."
    try:
        content = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return f"Error: '{path}' appears to be a binary file."
    if len(content) > _MAX_FILE_CONTENT_CHARS:
        content = content[:_MAX_FILE_CONTENT_CHARS] + f"\n... (truncated; {len(content)} total chars)"
    return content


def _get_default_branch_commit_sha(repo) -> str:
    default_branch = repo.default_branch
    branch = repo.get_branch(default_branch)
    return branch.commit.sha


def fetch_repo_context(
    github_url: str,
    *,
    max_files: int = 200,
    github_token_env: str = "GITHUB_TOKEN",
) -> RepoContext:
    """
    Fetch repo metadata (description, topics, languages) and filtered file tree.
    Uses the GitHub API via `PyGithub` (no raw HTTP).
    """
    ref = parse_github_repo_url(github_url)

    # Optional to avoid rate limits. PyGithub still works for public repos without a token.
    token = os.environ.get(github_token_env) or None

    try:
        gh = Github(login_or_token=token) if token else Github()
        repo = gh.get_repo(f"{ref.owner}/{ref.repo}")
        sha = _get_default_branch_commit_sha(repo)
        tree = repo.get_git_tree(sha, recursive=True)
        languages: Dict[str, int] = repo.get_languages()
        topics: List[str] = repo.get_topics()
    except GithubException as e:
        status = getattr(e, "status", None)
        message = str(e)
        if status == 404:
            raise RepoNotFoundError(message)
        if status == 401 or status == 403:
            raise RepoUnauthorizedError(message)
        raise RepoFetchError(message)
    except Exception as e:
        raise RepoFetchError(str(e))

    metadata = RepoMetadata(
        description=repo.description or None,
        topics=topics,
        languages=languages,
        default_branch=repo.default_branch,
        homepage=repo.homepage or None,
        stars=repo.stargazers_count,
    )

    paths: List[str] = []
    for entry in tree.tree:
        if entry.type != "blob":
            continue
        if not entry.path:
            continue
        if _is_excluded_path(entry.path):
            continue

        paths.append(entry.path)
        if len(paths) >= max_files:
            break

    if not paths:
        raise RepoEmptyError("Repo file list was empty after filtering.")

    # Keep deterministic order for stable prompts.
    paths = sorted(paths)

    # Fetch key files that exist in the repo
    paths_set = set(paths)
    key_files_content: List[KeyFileContent] = []
    for filename in _KEY_FILES:
        if filename not in paths_set:
            continue
        content = fetch_file_content(ref.owner, ref.repo, sha, filename)
        if len(content) > _MAX_KEY_FILE_CHARS:
            content = content[:_MAX_KEY_FILE_CHARS] + "\n... (truncated)"
        key_files_content.append(KeyFileContent(name=filename, content=content))

    return RepoContext(
        metadata=metadata,
        paths=paths,
        key_files_content=key_files_content,
        owner=ref.owner,
        repo_name=ref.repo,
        commit_sha=sha,
    )


def make_structure_tree(paths: Sequence[str], *, max_lines: int = 120) -> str:
    # "Tree" for the response, but we only have filenames; we render as a truncated list.
    # This is intentionally simple and stable for tests and parsing.
    shown = list(paths)[:max_lines]
    lines = ["Repository file tree (filenames only):"]
    lines.extend([f"- {p}" for p in shown])
    if len(paths) > max_lines:
        lines.append(f"... ({len(paths) - max_lines} more files)")
    return "\n".join(lines)

