"""Remembered library sources (~/.openground/sources.json)."""

import json
from typing import Literal, TypedDict

from openground.config import get_sources_path


class LibrarySource(TypedDict, total=False):
    type: Literal["git_repo", "sitemap", "local_path"]
    repo_url: str
    sitemap_url: str
    local_path: str
    docs_paths: list[str]
    filter_keywords: list[str]


def load_sources() -> dict[str, LibrarySource]:
    path = get_sources_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _write(sources: dict[str, LibrarySource]) -> None:
    path = get_sources_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")


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
