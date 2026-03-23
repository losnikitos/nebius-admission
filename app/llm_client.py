from __future__ import annotations

import json
import logging
import os
import re
from typing import List

from openai import OpenAI

from app.github_repo_fetcher import RepoContext, fetch_file_content, ls_directory

logger = logging.getLogger(__name__)


_NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1/"
_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
_MAX_TURNS = 20


_SYSTEM_PROMPT = """\
You are a code analyst. \
Your job is to summarize a GitHub repository, list technologies used and describe the structure of the repository. \
You will receive metadata and key files for a GitHub repository. \
In most cases this context is sufficient — call answer() directly without using any tools. \
Only call cat() if a specific file is clearly missing and would materially change the analysis. \
Only call ls() if the directory structure is genuinely ambiguous and cannot be inferred from the file tree. \
    
When you have enough information, call answer() with: \
- "summary": 2–4 sentence description of what the project does \
- "technologies": array of technology/language/framework names (no duplicates) \
- "structure": 2–3 sentence description of how the project is organised"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ls",
            "description": (
                "List immediate files and subdirectories inside a repository directory. "
                "Directories are shown with a trailing '/'. "
                "Use an empty string or '/' for the repo root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path relative to repo root, e.g. '' for root, 'src', 'packages/core'.",
                    }
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cat",
            "description": "Read the content of a file in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to repo root, e.g. 'README.md', 'src/main.py'.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer",
            "description": "Submit the final structured analysis. Call this when you have enough information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "2–4 sentence description of what the project does.",
                    },
                    "technologies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of technology/language/framework names (no duplicates).",
                    },
                    "structure": {
                        "type": "string",
                        "description": "2–3 sentence description of how the project is organised.",
                    },
                },
                "required": ["summary", "technologies", "structure"],
            },
        },
    },
]


def build_prompt(data: RepoContext) -> str:
    parts: list[str] = []

    parts.append(f"Repository: https://github.com/{data.owner}/{data.repo_name}")
    parts.append("")

    parts.append("== Metadata ==")
    if data.metadata.description:
        parts.append(f"Description: {data.metadata.description}")
    if data.metadata.topics:
        parts.append(f"Topics: {', '.join(data.metadata.topics)}")
    if data.metadata.languages:
        lang_summary = ", ".join(
            f"{lang} ({int(bytes_):,} bytes)"
            for lang, bytes_ in data.metadata.languages.items()
            if str(bytes_).isdigit()
        )
        parts.append(f"Languages: {lang_summary}")
    if data.metadata.homepage:
        parts.append(f"Homepage: {data.metadata.homepage}")

    parts.append("")
    parts.append("== Root listing ==")
    root_entries = ls_directory(data.paths, "")
    parts.append("\n".join(f"- {e}" for e in root_entries) or "(empty)")

    if data.key_files_content:
        parts.append("")
        parts.append("== Key files ==")
        for kf in data.key_files_content:
            parts.append(f"\n--- {kf.name} ---")
            parts.append(kf.content)

    parts.append("")
    parts.append(
        f"The above context is usually sufficient. Call answer() now unless a specific "
        f"critical file is missing. Use cat() or ls() only when truly necessary. "
        f"You have up to {_MAX_TURNS} tool-call turns total."
    )

    return "\n".join(parts)


def _dispatch_tool(name: str, args: dict, context: RepoContext) -> str:
    if name == "ls":
        directory = args.get("directory", "")
        entries = ls_directory(context.paths, directory)
        return "\n".join(entries) if entries else "(empty or directory not found)"

    if name == "cat":
        path = args.get("path", "")
        return fetch_file_content(context.owner, context.repo_name, context.commit_sha, path)

    return f"Unknown tool: {name}"


def _parse_technologies(value) -> List[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        items = re.split(r"[,;\n]+", value)
        return [item.strip() for item in items if item.strip()]
    return []


def summarize_repo(data: RepoContext) -> tuple[str, List[str], str]:
    """Run an agentic loop: let the LLM explore the repo via ls/cat tools, then collect answer()."""
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY environment variable is not set")

    client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=api_key)

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(data)},
    ]

    for turn in range(_MAX_TURNS):
        is_last = turn == _MAX_TURNS - 1
        tool_choice = (
            {"type": "function", "function": {"name": "answer"}} if is_last else "auto"
        )

        logger.info("LLM turn %d/%d", turn + 1, _MAX_TURNS)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=_TOOLS,
            tool_choice=tool_choice,
            max_tokens=2048,
            temperature=0.2,
        )

        msg = response.choices[0].message

        # Append assistant turn to history
        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            # Model returned plain text — try to parse as JSON fallback
            raw = (msg.content or "").strip()
            logger.info("LLM returned text with no tool call: %r", raw[:200])
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            try:
                data_out = json.loads(raw)
                return (
                    str(data_out.get("summary", "")),
                    _parse_technologies(data_out.get("technologies", [])),
                    str(data_out.get("structure", "")),
                )
            except json.JSONDecodeError:
                raise ValueError(f"LLM returned non-JSON text with no tool calls: {raw!r}")

        # Dispatch tool calls; check for answer()
        tool_results: list[dict] = []
        answer_result: dict | None = None

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name == "answer":
                answer_result = fn_args
                logger.info("LLM called answer()")
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "Answer recorded.",
                })
            else:
                logger.info("LLM called %s(%s)", fn_name, fn_args)
                result = _dispatch_tool(fn_name, fn_args, data)
                logger.debug("%s → %d chars", fn_name, len(result))
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        messages.extend(tool_results)

        if answer_result is not None:
            return (
                str(answer_result.get("summary", "")),
                _parse_technologies(answer_result.get("technologies", [])),
                str(answer_result.get("structure", "")),
            )

        # Inform the LLM how many turns are left before the next call.
        turns_left = _MAX_TURNS - (turn + 1)
        if turns_left == 1:
            messages.append({
                "role": "user",
                "content": "1 turn remaining — this is your last chance. Call answer() now.",
            })
        elif turns_left > 1:
            messages.append({
                "role": "user",
                "content": f"{turns_left} turns remaining.",
            })

    raise ValueError("LLM did not call answer() within the allowed turns")
