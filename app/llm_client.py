from __future__ import annotations

import json
import os
from typing import List

from openai import OpenAI

from app.github_repo_fetcher import RepoContext


_NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1/"
_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"


def build_prompt(ctx: RepoContext) -> str:
    meta = ctx.metadata

    parts: list[str] = []

    parts.append("== Repository Metadata ==")
    if meta.description:
        parts.append(f"Description: {meta.description}")
    if meta.topics:
        parts.append(f"Topics: {', '.join(meta.topics)}")
    if meta.languages:
        lang_summary = ", ".join(
            f"{lang} ({bytes_:,} bytes)"
            for lang, bytes_ in meta.languages.items()
            if isinstance(bytes_, int)
        )
        parts.append(f"Languages: {lang_summary}")
    if meta.homepage:
        parts.append(f"Homepage: {meta.homepage}")
    parts.append(f"Stars: {meta.stars}")
    parts.append(f"Default branch: {meta.default_branch}")

    parts.append("")
    parts.append("== File List ==")
    for path in ctx.paths:
        parts.append(f"- {path}")

    return "\n".join(parts)


_SYSTEM_PROMPT = """\
You are a code analyst. Given repository metadata and a file list, produce a JSON object with exactly three fields:
- "summary": a 2–4 sentence human-readable description of what the project does
- "technologies": a JSON array of technology/language/framework names used (strings, no duplicates)
- "structure": a 2–3 sentence description of how the project is organized

Respond with valid JSON only — no markdown fences, no extra text."""


def summarize_repo(ctx: RepoContext) -> tuple[str, List[str], str]:
    """Call the Nebius LLM and return (summary, technologies, structure)."""
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY environment variable is not set")

    client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=api_key)

    user_content = build_prompt(ctx)

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=512,
        temperature=0.2,
    )

    raw = response.choices[0].message.content or ""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON response: {raw!r}") from e

    summary = str(data.get("summary", ""))
    technologies = [str(t) for t in data.get("technologies", [])]
    structure = str(data.get("structure", ""))

    return summary, technologies, structure
