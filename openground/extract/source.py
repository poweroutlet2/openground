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


def get_source_file_path(custom_path: Optional[Path] = None) -> Path:
    """Get the path to the sources.json file.
    
    Args:
        custom_path: Optional custom path to sources.json file. If provided, this path is used.
    
    Returns:
        Path to the sources.json file.
    """
    if custom_path is not None:
        return Path(custom_path).expanduser()
    
    # Try looking in the same directory as this file first (if installed as package)
    pkg_source_file = Path(__file__).parent / "sources.json"
    if pkg_source_file.exists():
        return pkg_source_file

    # Fallback to project root for development
    root_source_file = Path(__file__).parent.parent / "sources.json"
    if root_source_file.exists():
        return root_source_file

    return pkg_source_file


def load_source_file(custom_path: Optional[Path] = None) -> dict[str, LibrarySource]:
    """Load the library source file from sources.json.
    
    Args:
        custom_path: Optional custom path to sources.json file. If provided, this path is used.
    
    Returns:
        Dictionary mapping library names to their source configurations.
    """
    path = get_source_file_path(custom_path)
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_library_config(name: str, custom_path: Optional[Path] = None) -> Optional[LibrarySource]:
    """Get the configuration for a specific library by name.
    
    Args:
        name: Name of the library to get configuration for.
        custom_path: Optional custom path to sources.json file. If provided, this path is used.
    
    Returns:
        Library source configuration if found, None otherwise.
    """
    source_file = load_source_file(custom_path)
    return source_file.get(name)
