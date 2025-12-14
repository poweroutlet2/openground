# Shared defaults for CLI command

import os
from pathlib import Path


def get_data_home() -> Path:
    """Get the base directory for openground data.

    Uses XDG_DATA_HOME if set, otherwise defaults to ~/.local/share/openground
    on Linux/macOS or ~/AppData/Local/openground on Windows.
    """
    if xdg_data := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data) / "openground"

    # Platform-specific defaults
    if os.name == "nt":  # Windows
        return Path.home() / "AppData" / "Local" / "openground"
    else:  # Linux, macOS, etc.
        return Path.home() / ".local" / "share" / "openground"


DEFAULT_LIBRARY_NAME = "databricks_docs"

# Extraction defaults
SITEMAP_URL = "https://docs.databricks.com/aws/en/sitemap.xml"
CONCURRENCY_LIMIT = 50
FILTER_KEYWORDS = ["docs", "documentation", "blog"]


def get_raw_data_dir(library_name: str) -> Path:
    """Construct the path to the raw data directory for a given library name."""
    return get_data_home() / "raw_data" / library_name.lower()


DEFAULT_RAW_DATA_DIR = get_raw_data_dir(DEFAULT_LIBRARY_NAME)

# Ingestion / query defaults
DEFAULT_DB_PATH = get_data_home() / "lancedb"
DEFAULT_TABLE_NAME = "documents"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
