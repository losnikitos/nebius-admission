from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple
from urllib.parse import urlparse

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


def parse_github_repo_url(github_url: str) -> RepoRef:
    match = _GITHUB_REPO_URL_RE.match(github_url.strip())
    if not match:
        raise ValueError("Invalid github_url. Expected public GitHub repo URL.")
    return RepoRef(owner=match.group("owner"), repo=match.group("repo"))


# These are "unsafe for LLM context" heuristics: binaries, build artifacts, vendor deps, etc.
_EXCLUDED_DIR_PREFIXES: Sequence[str] = (
    ".git/",
    "node_modules/",
    "bower_components/",
    "dist/",
    "build/",
    "target/",
    "out/",
    "coverage/",
    ".pytest_cache/",
    ".mypy_cache/",
    "__pycache__/",
    ".venv/",
    "venv/",
)

_EXCLUDED_FILE_EXTENSIONS: Sequence[str] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".rar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".wasm",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".eot",
    ".ttf",
    ".woff",
    ".woff2",
    ".map",
)

_EXCLUDED_LOCK_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "poetry.lock",
    "Pipfile.lock",
    "requirements-dev.txt",
}


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


def _guess_technologies_from_paths(paths: Iterable[str]) -> List[str]:
    techs: List[str] = []

    def add_once(name: str) -> None:
        if name not in techs:
            techs.append(name)

    ext_to_tech = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".cpp": "C++",
        ".c": "C",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".m": "Objective-C",
        ".scala": "Scala",
    }

    for p in paths:
        lower = p.lower()
        for ext, tech in ext_to_tech.items():
            if lower.endswith(ext):
                add_once(tech)
                break

        # Basic framework hints from common filenames.
        if lower.endswith("requirements.txt") or lower == "pyproject.toml":
            add_once("Python")
        if lower.startswith("src/") and any(
            lower.endswith(ext) for ext in (".py", ".ts", ".js", ".java")
        ):
            # Keep it light; will likely already have language from extension.
            pass

    return techs


def guess_technologies_from_paths(paths: Iterable[str]) -> List[str]:
    return _guess_technologies_from_paths(paths)


def _get_default_branch_commit_sha(repo) -> str:
    default_branch = repo.default_branch
    branch = repo.get_branch(default_branch)
    return branch.commit.sha


def fetch_repo_file_paths(
    github_url: str,
    *,
    max_files: int = 200,
    github_token_env: str = "GITHUB_TOKEN",
) -> List[str]:
    """
    Fetch a repo's file tree as a list of file paths (filenames only).
    Uses the GitHub API via `PyGithub` (no raw HTTP).
    """
    ref = parse_github_repo_url(github_url)

    token = None
    # Optional to avoid rate limits. If missing, PyGithub still works for public repos.
    try:
        import os

        token = os.environ.get(github_token_env) or None
    except Exception:
        token = None

    try:
        gh = Github(login_or_token=token) if token else Github()
        repo = gh.get_repo(f"{ref.owner}/{ref.repo}")
        sha = _get_default_branch_commit_sha(repo)
        tree = repo.get_git_tree(sha, recursive=True)
    except GithubException as e:
        status = getattr(e, "status", None)
        message = str(e)
        if status == 404:
            raise RepoNotFoundError(message)
        if status == 401 or status == 403:
            # Can be "private repo", "rate limited", or other auth failures.
            if "rate limit" in message.lower():
                raise RepoUnauthorizedError(message)
            raise RepoUnauthorizedError(message)
        raise RepoFetchError(message)
    except Exception as e:
        raise RepoFetchError(str(e))

    paths: List[str] = []
    for entry in getattr(tree, "tree", []) or []:
        entry_type = getattr(entry, "type", None)
        if entry_type != "blob":
            continue

        entry_path = getattr(entry, "path", None)
        if not entry_path:
            continue
        if _is_excluded_path(entry_path):
            continue

        paths.append(entry_path)
        if len(paths) >= max_files:
            break

    if not paths:
        raise RepoEmptyError("Repo file list was empty after filtering.")

    # Keep deterministic order for stable prompts.
    paths = sorted(paths)
    return paths


def make_structure_tree(paths: Sequence[str], *, max_lines: int = 120) -> str:
    # "Tree" for the response, but we only have filenames; we render as a truncated list.
    # This is intentionally simple and stable for tests and parsing.
    shown = list(paths)[:max_lines]
    lines = ["Repository file tree (filenames only):"]
    lines.extend([f"- {p}" for p in shown])
    if len(paths) > max_lines:
        lines.append(f"... ({len(paths) - max_lines} more files)")
    return "\n".join(lines)

