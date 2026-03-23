"""Deterministic repository data fetcher.

Fetches repo metadata, root-level file listing, and content of key files,
then returns a RepoData structure ready for prompt interpolation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import tomllib
from github import Github
from github.GithubException import GithubException

from app.github_repo_fetcher import (
    RepoEmptyError,
    RepoFetchError,
    RepoNotFoundError,
    RepoUnauthorizedError,
    fetch_file_content,
    parse_github_repo_url,
)


_FILTER_CONFIG_PATH = Path(__file__).resolve().parent / "repo_filter_config.toml"
_FILTER_CONFIG = tomllib.loads(_FILTER_CONFIG_PATH.read_text(encoding="utf-8"))
_KEY_FILES: List[str] = _FILTER_CONFIG.get("key_files", [])
_KEY_FILES_SET: set[str] = set(_KEY_FILES)

_MAX_KEY_FILE_CHARS = 12_000


@dataclass(frozen=True)
class KeyFileContent:
    name: str
    content: str


@dataclass(frozen=True)
class RepoData:
    owner: str
    repo_name: str
    description: Optional[str]
    topics: List[str]
    languages: Dict[str, int]
    homepage: Optional[str]
    # Immediate children of the root (files and directory names ending with /)
    root_files: List[str]
    # Content of key files that were found at the root of the repo
    key_files_content: List[KeyFileContent] = field(default_factory=list)


def fetch_repo_data(
    github_url: str,
    *,
    github_token_env: str = "GITHUB_TOKEN",
) -> RepoData:
    """Fetch deterministic repo data: metadata + root listing + key file contents."""
    ref = parse_github_repo_url(github_url)
    token = os.environ.get(github_token_env) or None

    try:
        gh = Github(login_or_token=token) if token else Github()
        repo = gh.get_repo(f"{ref.owner}/{ref.repo}")
        default_branch = repo.default_branch
        sha = repo.get_branch(default_branch).commit.sha
        tree = repo.get_git_tree(sha, recursive=True)
        languages: Dict[str, int] = repo.get_languages()
        topics: List[str] = repo.get_topics()
    except GithubException as e:
        status = getattr(e, "status", None)
        message = str(e)
        if status == 404:
            raise RepoNotFoundError(message)
        if status in (401, 403):
            raise RepoUnauthorizedError(message)
        raise RepoFetchError(message)
    except Exception as e:
        raise RepoFetchError(str(e))

    # Collect all blob paths for key-file lookup
    all_paths: set[str] = set()
    for entry in tree.tree:
        if entry.type == "blob" and entry.path:
            all_paths.add(entry.path)

    if not all_paths:
        raise RepoEmptyError("Repository has no files.")

    # Root-level listing: immediate children (files and dirs)
    root_entries: set[str] = set()
    for path in all_paths:
        slash = path.find("/")
        if slash == -1:
            root_entries.add(path)
        else:
            root_entries.add(path[:slash] + "/")
    root_files = sorted(root_entries)

    # Fetch content for key files that exist at the root
    key_files_content: List[KeyFileContent] = []
    for filename in _KEY_FILES:
        if filename not in all_paths:
            continue
        content = fetch_file_content(ref.owner, ref.repo, sha, filename)
        if len(content) > _MAX_KEY_FILE_CHARS:
            content = content[:_MAX_KEY_FILE_CHARS] + f"\n... (truncated)"
        key_files_content.append(KeyFileContent(name=filename, content=content))

    return RepoData(
        owner=ref.owner,
        repo_name=ref.repo,
        description=repo.description or None,
        topics=topics,
        languages=languages,
        homepage=repo.homepage or None,
        root_files=root_files,
        key_files_content=key_files_content,
    )
