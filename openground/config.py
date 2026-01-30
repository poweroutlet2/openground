# Shared defaults for CLI command

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def get_data_home() -> Path:
    """Get the base directory for openground data.

    Uses XDG_DATA_HOME if set, otherwise defaults to ~/.local/share/openground
    on Linux/macOS or ~/AppData/Local/openground on Windows.
    """
    if xdg_data := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data).expanduser() / "openground"

    # Platform-specific defaults
    if os.name == "nt":  # Windows
        return Path.home() / "AppData" / "Local" / "openground"
    else:  # Linux, macOS, etc.
        return Path.home() / ".local" / "share" / "openground"


DEFAULT_LIBRARY_NAME = "openground_docs"

# Extraction defaults
SITEMAP_URL = "https://docs.openground.ai/sitemap.xml"
CONCURRENCY_LIMIT = 50


DEFAULT_RAW_DATA_DIR_BASE = get_data_home() / "raw_data"
# User's personal sources file (shared across all projects)
USER_SOURCE_FILE = Path.home() / ".openground" / "sources.json"
# Project-local sources file (for project-specific overrides)
PROJECT_SOURCE_FILE = Path(".openground") / "sources.json"


def get_library_raw_data_dir(library_name: str, version: str) -> Path:
    """Construct the path to the raw data directory for a given library name and version.

    Args:
        library_name: Name of the library.
        version: Version string.

    Returns:
        Path to the raw data directory.
    """
    config = get_effective_config()
    raw_data_dir_base = Path(config.get("raw_data_dir", str(DEFAULT_RAW_DATA_DIR_BASE)))
    return raw_data_dir_base / library_name.lower() / version


# Embeddings / query defaults
DEFAULT_DB_PATH = get_data_home() / "lancedb"
DEFAULT_TABLE_NAME = "documents"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_LIBRARY_VERSION = "latest"
DEFAULT_EMBEDDING_DIMENSIONS = 384
# fastembed or sentence-transformers
DEFAULT_EMBEDDING_BACKEND = "fastembed"

# Default values for embeddings parameters
DEFAULT_BATCH_SIZE = 32
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 200
# Default values for query parameters
DEFAULT_TOP_K = 5


def get_config_path() -> Path:
    """Get the path to the user's config file.

    Uses XDG_CONFIG_HOME if set, otherwise defaults to ~/.config/openground
    on Linux/macOS or ~/AppData/Local/openground on Windows.
    """
    if xdg_config := os.environ.get("XDG_CONFIG_HOME"):
        config_dir = Path(xdg_config).expanduser() / "openground"
    elif os.name == "nt":  # Windows
        config_dir = Path.home() / "AppData" / "Local" / "openground"
    else:  # Linux, macOS, etc.
        config_dir = Path.home() / ".config" / "openground"

    return config_dir / "config.json"


# Cache for loaded config
_config_cache: dict[str, Any] | None = None


def load_config() -> dict[str, Any]:
    """Load configuration from the config file.

    Returns empty dict if file doesn't exist.
    Raises ValueError if file contains invalid JSON.
    """
    config_path = get_config_path()

    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {config_path}: {e}") from e
    except Exception as e:
        raise ValueError(f"Error reading config file {config_path}: {e}") from e


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to the config file atomically.

    Creates the config directory if it doesn't exist.
    """
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write atomically: write to temp file, then rename
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            json.dump(config, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)

        # Atomic rename
        tmp_path.replace(config_path)
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise


def get_default_config() -> dict[str, Any]:
    """Get the default configuration dictionary."""
    return {
        "db_path": str(DEFAULT_DB_PATH),
        "table_name": DEFAULT_TABLE_NAME,
        "raw_data_dir": str(DEFAULT_RAW_DATA_DIR_BASE),
        "extraction": {
            "concurrency_limit": CONCURRENCY_LIMIT,
        },
        "embeddings": {
            "batch_size": DEFAULT_BATCH_SIZE,
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "embedding_dimensions": DEFAULT_EMBEDDING_DIMENSIONS,
            "embedding_backend": DEFAULT_EMBEDDING_BACKEND,
        },
        "query": {
            "top_k": DEFAULT_TOP_K,
        },
        "sources": {
            "auto_add_local": True,
        },
    }


def _merge_with_defaults(user_config: dict[str, Any]) -> dict[str, Any]:
    """Merge user config with hardcoded defaults."""
    # Start with defaults
    merged = get_default_config()

    # Override with user config
    if "db_path" in user_config:
        merged["db_path"] = user_config["db_path"]
    if "table_name" in user_config:
        merged["table_name"] = user_config["table_name"]
    if "raw_data_dir" in user_config:
        merged["raw_data_dir"] = user_config["raw_data_dir"]

    if "extraction" in user_config:
        if not isinstance(user_config["extraction"], dict):
            raise ValueError(
                "Config key 'extraction' must be an object. Hint: If you need to reset the default config, run `openground config reset`."
            )
        merged["extraction"].update(user_config["extraction"])
    if "embeddings" in user_config:
        if not isinstance(user_config["embeddings"], dict):
            raise ValueError(
                "Config key 'embeddings' must be an object. Hint: If you need to reset the default config, run `openground config reset`."
            )
        merged["embeddings"].update(user_config["embeddings"])
    if "query" in user_config:
        if not isinstance(user_config["query"], dict):
            raise ValueError(
                "Config key 'query' must be an object. Hint: If you need to reset the default config, run `openground config reset`."
            )
        merged["query"].update(user_config["query"])

    if "sources" in user_config:
        if not isinstance(user_config["sources"], dict):
            raise ValueError(
                "Config key 'sources' must be an object. Hint: If you need to reset the default config, run `openground config reset`."
            )
        merged["sources"].update(user_config["sources"])

    return merged


def get_effective_config() -> dict[str, Any]:
    """Get the effective configuration (user config merged with defaults).

    Returns merged config (user config overrides defaults).
    Does not create the config file if it doesn't exist - use ensure_config_exists()
    or create it explicitly before calling this function.
    Caches the result for the duration of the process.
    """
    global _config_cache
    if _config_cache is None:
        user_config = load_config()
        _config_cache = _merge_with_defaults(user_config)
    return _config_cache


def clear_config_cache() -> None:
    """Clear the config cache. Used after config modifications."""
    global _config_cache
    _config_cache = None
