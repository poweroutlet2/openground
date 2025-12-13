# Shared defaults for CLI command

from pathlib import Path


DEFAULT_LIBRARY_NAME = "databricks_docs"

# Extraction defaults
SITEMAP_URL = "https://docs.databricks.com/aws/en/sitemap.xml"
CONCURRENCY_LIMIT = 50
FILTER_KEYWORDS = ["docs", "documentation", "blog"]


def get_raw_data_dir(library_name: str) -> Path:
    """Construct the path to the raw data directory for a given library name."""
    return Path(f"raw_data/{library_name.lower()}")


DEFAULT_RAW_DATA_DIR = get_raw_data_dir(DEFAULT_LIBRARY_NAME)

# Ingestion / query defaults
DEFAULT_DB_PATH = Path(".lancedb")
DEFAULT_TABLE_NAME = "documents"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
