"""MCP tool call counters, stored next to the database."""

import json
import tempfile
from pathlib import Path

from openground.config import get_data_home
from openground.console import UserError

TOOLS = ("search_documents_tool", "list_libraries_tool", "get_full_content_tool")


def get_stats_path() -> Path:
    return get_data_home() / "stats.json"


def load_tool_calls() -> dict[str, int]:
    calls = dict.fromkeys(TOOLS, 0)
    path = get_stats_path()
    if path.exists():
        try:
            calls.update(
                json.loads(path.read_text(encoding="utf-8") or "{}")["tool_calls"]
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise UserError(
                f"Invalid stats file {path}: {e}\nRun `openground stats --reset` to fix it."
            )
    return calls


def save_tool_calls(calls: dict[str, int]) -> None:
    path = get_stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump({"tool_calls": calls}, tmp, indent=2)
    Path(tmp.name).replace(path)


def increment_tool_call(tool_name: str) -> None:
    try:
        calls = load_tool_calls()
    except UserError:
        calls = dict.fromkeys(TOOLS, 0)
    calls[tool_name] = calls.get(tool_name, 0) + 1
    save_tool_calls(calls)


def reset_stats() -> None:
    save_tool_calls(dict.fromkeys(TOOLS, 0))
