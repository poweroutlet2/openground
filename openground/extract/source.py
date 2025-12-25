import json
from pathlib import Path
from typing import TypedDict, Literal, Optional, List


class LibrarySource(TypedDict, total=False):
    type: Literal["sitemap", "git_repo"]
    sitemap_url: str
    repo_url: str
    filter_keywords: List[str]
    languages: List[str]
    docs_paths: List[str]


def get_source_file_path() -> Path:
    """Get the path to the sources.json file."""
    # Try looking in the same directory as this file first (if installed as package)
    pkg_source_file = Path(__file__).parent / "sources.json"
    if pkg_source_file.exists():
        return pkg_source_file

    # Fallback to project root for development
    root_source_file = Path(__file__).parent.parent / "sources.json"
    if root_source_file.exists():
        return root_source_file

    return pkg_source_file


def load_source_file() -> dict[str, LibrarySource]:
    """Load the library source file from sources.json."""
    path = get_source_file_path()
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_library_config(name: str) -> Optional[LibrarySource]:
    """Get the configuration for a specific library by name."""
    source_file = load_source_file()
    return source_file.get(name)
