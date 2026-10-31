"""Remembered library sources (sources.json next to config.json)."""

import json
from typing import Literal, TypedDict

from openground.config import get_sources_path
from openground.console import UserError


class LibrarySource(TypedDict, total=False):
    type: Literal["git_repo", "sitemap", "local_path"]
    repo_url: str
    sitemap_url: str
    local_path: str
    docs_paths: list[str]
    filter_keywords: list[str]


SOURCE_FIELD = {
    "git_repo": "repo_url",
    "sitemap": "sitemap_url",
    "local_path": "local_path",
}


def _validate(path, data) -> dict[str, LibrarySource]:
    def bad(problem: str) -> UserError:
        return UserError(
            f"Invalid sources file {path}: {problem}\nFix or delete the file."
        )

    if not isinstance(data, dict):
        raise bad("top level must be an object mapping library names to sources")
    for name, entry in data.items():
        if not isinstance(entry, dict) or entry.get("type") not in SOURCE_FIELD:
            raise bad(f"entry '{name}' needs a type of {', '.join(SOURCE_FIELD)}")
        field = SOURCE_FIELD[entry["type"]]
        if not isinstance(entry.get(field), str) or not entry[field]:
            raise bad(f"entry '{name}' ({entry['type']}) is missing '{field}'")
        for key in ("docs_paths", "filter_keywords"):
            value = entry.get(key, [])
            if not isinstance(value, list) or not all(
                isinstance(v, str) for v in value
            ):
                raise bad(f"entry '{name}': '{key}' must be a list of strings")
    return data


def load_sources() -> dict[str, LibrarySource]:
    path = get_sources_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise UserError(f"Invalid sources file {path}: {e}\nFix or delete the file.")
    return _validate(path, data)


def _write(sources: dict[str, LibrarySource]) -> None:
    path = get_sources_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")


def source_location(source: LibrarySource) -> str:
    return source[SOURCE_FIELD[source["type"]]]


def get_source(library_name: str) -> LibrarySource | None:
    return load_sources().get(library_name)


def save_source(library_name: str, source: LibrarySource) -> None:
    _write({**load_sources(), library_name: source})


def remove_source(library_name: str) -> bool:
    sources = load_sources()
    if sources.pop(library_name, None) is None:
        return False
    _write(sources)
    return True
