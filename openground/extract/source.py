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

    Priority order:
    1. Custom path (if provided)
    2. Project-local .openground/sources.json (if exists)
    3. User ~/.openground/sources.json (if exists)
    4. Package-level sources.json
    5. Project root sources.json (development)

    Args:
        custom_path: Optional custom path to sources.json file. If provided, this path is used.

    Returns:
        Path to the sources.json file.
    """
    if custom_path is not None:
        return Path(custom_path).expanduser()

    from openground.config import PROJECT_SOURCE_FILE, USER_SOURCE_FILE

    # Check project-local first (allows project-specific overrides)
    if PROJECT_SOURCE_FILE.exists():
        return PROJECT_SOURCE_FILE

    # Then check user sources (shared across projects)
    if USER_SOURCE_FILE.exists():
        return USER_SOURCE_FILE

    # Package-level fallback
    pkg_source_file = Path(__file__).parent / "sources.json"
    if pkg_source_file.exists():
        return pkg_source_file

    # Development fallback
    root_source_file = Path(__file__).parent.parent / "sources.json"
    if root_source_file.exists():
        return root_source_file

    return pkg_source_file


def save_source_to_sources(library_name: str, config: LibrarySource) -> None:
    """Save a library source configuration to both project-local and user sources files.

    Saves to:
    - .openground/sources.json (project-local, for project-specific setup)
    - ~/.openground/sources.json (user home, shared across all projects)

    Args:
        library_name: Name of the library.
        config: Source configuration to save.
    """
    from openground.config import USER_SOURCE_FILE, PROJECT_SOURCE_FILE

    def _save_to_file(file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        sources = {}
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    sources = json.load(f)
                except json.JSONDecodeError:
                    sources = {}

        sources[library_name] = config

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(sources, f, indent=2, ensure_ascii=False)

    # Save to both project-local and user source files
    _save_to_file(PROJECT_SOURCE_FILE)
    _save_to_file(USER_SOURCE_FILE)


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

    Priority order:
    1. Custom path (if provided)
    2. Project-local .openground/sources.json (allows project-specific overrides)
    3. User ~/.openground/sources.json (shared across all projects)
    4. Package-level sources.json
    5. Project root sources.json (for development)

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

    # 2. Project-local sources (allows project-specific overrides)
    from openground.config import PROJECT_SOURCE_FILE, USER_SOURCE_FILE

    paths_to_check.append(PROJECT_SOURCE_FILE)

    # 3. User sources (shared across all projects)
    paths_to_check.append(USER_SOURCE_FILE)

    # 4. Package level sources file
    pkg_source_file = Path(__file__).parent / "sources.json"
    paths_to_check.append(pkg_source_file)

    # 5. Project root sources file (for development)
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
