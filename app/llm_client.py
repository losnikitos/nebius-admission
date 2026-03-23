from __future__ import annotations

import json
import os
from typing import List

from openai import OpenAI

from app.github_repo_fetcher import RepoContext, fetch_file_content, ls_directory


_NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1/"
_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"

_MAX_TOOL_CALLS = 20

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
    parts.append(
        "Use the `ls` and `cat` tools to explore the repository "
        "(README, entry points, config, key source files). "
        "When you have enough information call `answer`."
    )

    return "\n".join(parts)


_SYSTEM_PROMPT = """\
You are a code analyst exploring a GitHub repository. You have three tools:
- `ls(path)`: list immediate children of a directory (use "" for root).
- `cat(path)`: read the content of a file.
- `answer(summary, technologies, structure)`: submit your final analysis.

Explore the repo using `ls` and `cat`, then call `answer` with:
- "summary": 2–4 sentence description of what the project does
- "technologies": array of technology/language/framework names (no duplicates)
- "structure": 2–3 sentence description of how the project is organised"""


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ls",
            "description": "List files and immediate subdirectories at the given repository path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to repo root. Use empty string for root.",
                    }
                },
                "required": ["path"],
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
                        "description": "File path relative to repo root.",
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
            "description": "Submit the final repository analysis. Call this when you have gathered enough information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "2–4 sentence human-readable description of what the project does.",
                    },
                    "technologies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of technologies/languages/frameworks used (no duplicates).",
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


def _execute_tool(name: str, args: dict, ctx: RepoContext) -> str:
    if name == "ls":
        entries = ls_directory(ctx.paths, args.get("path", ""))
        return "\n".join(entries) if entries else "(empty or no matching files)"
    if name == "cat":
        return fetch_file_content(ctx.owner, ctx.repo_name, ctx.commit_sha, args.get("path", ""))
    return f"Unknown tool: {name}"


def summarize_repo(ctx: RepoContext) -> tuple[str, List[str], str]:
    """Run an agentic tool loop and return (summary, technologies, structure)."""
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError("NEBIUS_API_KEY environment variable is not set")

    client = OpenAI(base_url=_NEBIUS_BASE_URL, api_key=api_key)

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(ctx)},
    ]

    for _ in range(_MAX_TOOL_CALLS):
        response = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.2,
        )

        msg = response.choices[0].message
        # Append assistant turn (serialise tool_calls for the history)
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
            raw = msg.content or ""
            try:
                data = json.loads(raw)
                return (
                    str(data.get("summary", "")),
                    [str(t) for t in data.get("technologies", [])],
                    str(data.get("structure", "")),
                )
            except json.JSONDecodeError:
                raise ValueError(f"LLM returned no tool call and non-JSON text: {raw!r}")

        # Process tool calls
        answer: dict | None = None
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if name == "answer":
                answer = args
                # Still need to ack the tool call so the history is valid
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": "Answer submitted.",
                })
            else:
                result = _execute_tool(name, args, ctx)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        if answer is not None:
            return (
                str(answer.get("summary", "")),
                [str(t) for t in answer.get("technologies", [])],
                str(answer.get("structure", "")),
            )

    raise ValueError(f"LLM did not call `answer` within {_MAX_TOOL_CALLS} tool calls.")
