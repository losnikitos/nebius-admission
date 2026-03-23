from __future__ import annotations

import json
import logging
import os
import re
from typing import List

from openai import OpenAI

from app.repo_data import RepoData

logger = logging.getLogger(__name__)


_NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1/"
_MODEL = "nvidia/nemotron-3-super-120b-a12b"


_SYSTEM_PROMPT = """\
You are a code analyst. You will be given information about a GitHub repository \
and must return a JSON object with exactly three keys:
- "summary": 2–4 sentence description of what the project does
- "technologies": array of technology/language/framework names (no duplicates)
- "structure": 2–3 sentence description of how the project is organised

Respond with valid JSON only. No markdown fences, no extra text."""


def build_prompt(data: RepoData) -> str:
    parts: list[str] = []

    parts.append(f"Repository: https://github.com/{data.owner}/{data.repo_name}")
    parts.append("")

    parts.append("== Metadata ==")
    if data.description:
        parts.append(f"Description: {data.description}")
    if data.topics:
        parts.append(f"Topics: {', '.join(data.topics)}")
    if data.languages:
        lang_summary = ", ".join(
            f"{lang} ({bytes_:,} bytes)"
            for lang, bytes_ in data.languages.items()
            if isinstance(bytes_, int)
        )
        parts.append(f"Languages: {lang_summary}")
    if data.homepage:
        parts.append(f"Homepage: {data.homepage}")

    parts.append("")
    parts.append("== Root-level files ==")
    parts.append("\n".join(data.root_files) or "(empty)")

    if data.key_files_content:
        parts.append("")
        parts.append("== Key files ==")
        for kf in data.key_files_content:
            parts.append(f"\n--- {kf.name} ---")
            parts.append(kf.content)

    return "\n".join(parts)


def _parse_technologies(value) -> List[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        items = re.split(r"[,;\n]+", value)
        return [item.strip() for item in items if item.strip()]
    return []


def summarize_repo(data: RepoData) -> tuple[str, List[str], str]:
    """Call the LLM once with the pre-fetched repo data and return (summary, technologies, structure)."""
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY environment variable is not set")

    client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=api_key)

    user_prompt = build_prompt(data)
    logger.info("Sending prompt to LLM (%d chars)", len(user_prompt))

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1024,
        temperature=0.2,
    )

    raw = (response.choices[0].message.content or "").strip()
    logger.info("LLM raw response (%d chars): %r", len(raw), raw[:200])

    # Strip optional markdown fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        data_out = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON response: {raw!r}") from e

    return (
        str(data_out.get("summary", "")),
        _parse_technologies(data_out.get("technologies", [])),
        str(data_out.get("structure", "")),
    )
