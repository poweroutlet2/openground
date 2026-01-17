import json
from pathlib import Path
from typing import TypedDict, Literal


class LibrarySource(TypedDict, total=False):
    type: Literal["sitemap", "git_repo"]
    sitemap_url: str
    repo_url: str
    filter_keywords: list[str]
    languages: list[str]
    docs_paths: list[str]


def get_source_file_path(custom_path: Path | None = None) -> Path:
    """Get the path to the sources.json file.

    Args:
        custom_path: Optional custom path to sources.json file. If provided, this path is used.

    Returns:
        Path to the sources.json file.
    """
    if custom_path is not None:
        return Path(custom_path).expanduser()

    # Check for local sources file first
    from openground.config import DEFAULT_LOCAL_SOURCE_FILE

    if DEFAULT_LOCAL_SOURCE_FILE.exists():
        return DEFAULT_LOCAL_SOURCE_FILE

    # Try looking in the same directory as this file first (if installed as package)
    pkg_source_file = Path(__file__).parent / "sources.json"
    if pkg_source_file.exists():
        return pkg_source_file

    # Fallback to project root for development
    root_source_file = Path(__file__).parent.parent / "sources.json"
    if root_source_file.exists():
        return root_source_file

    return pkg_source_file


def save_source_to_local(library_name: str, config: LibrarySource) -> None:
    """Save a library source configuration to the local .openground/sources.json file.

    Args:
        library_name: Name of the library.
        config: Source configuration to save.
    """
    from openground.config import DEFAULT_LOCAL_SOURCE_FILE

    DEFAULT_LOCAL_SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)

    sources = {}
    if DEFAULT_LOCAL_SOURCE_FILE.exists():
        with open(DEFAULT_LOCAL_SOURCE_FILE, "r", encoding="utf-8") as f:
            try:
                sources = json.load(f)
            except json.JSONDecodeError:
                # If file is invalid, start fresh
                sources = {}

    sources[library_name] = config

    with open(DEFAULT_LOCAL_SOURCE_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2, ensure_ascii=False)


def load_source_file(custom_path: Path | None = None) -> dict[str, LibrarySource]:
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


def get_library_config(
    name: str, custom_path: Path | None = None
) -> tuple[LibrarySource | None, Path | None]:
    """Get the configuration for a specific library by name by searching multiple sources.

    Args:
        name: Name of the library to get configuration for.
        custom_path: Optional custom path to sources.json file. If provided, this path is searched first.

    Returns:
        A tuple of (Library source configuration if found, Path to the file where it was found).
        Both are None if not found.
    """
    paths_to_check: list[Path] = []
    
    # 1. Custom path if provided
    if custom_path:
        paths_to_check.append(Path(custom_path).expanduser())

    # 2. Local sources file
    from openground.config import DEFAULT_LOCAL_SOURCE_FILE
    paths_to_check.append(DEFAULT_LOCAL_SOURCE_FILE)

    # 3. Package level sources file
    pkg_source_file = Path(__file__).parent / "sources.json"
    paths_to_check.append(pkg_source_file)

    # 4. Project root sources file (for development)
    root_source_file = Path(__file__).parent.parent / "sources.json"
    paths_to_check.append(root_source_file)

    for path in paths_to_check:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                try:
                    sources = json.load(f)
                    if name in sources:
                        return sources[name], path
                except (json.JSONDecodeError, PermissionError):
                    continue

    return None, None
