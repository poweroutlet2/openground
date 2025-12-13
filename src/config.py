# Shared defaults for CLI command

from pathlib import Path


DEFAULT_COLLECTION_TITLE = "Databricks"

# Extraction defaults
SITEMAP_URL = "https://docs.databricks.com/aws/en/sitemap.xml"
CONCURRENCY_LIMIT = 50
FILTER_KEYWORDS = ["docs", "documentation", "blog"]


def default_output_dir(collection_title: str = DEFAULT_COLLECTION_TITLE) -> str:
    return f"raw_data/docs/{collection_title}"


def default_raw_data_dir(collection_title: str = DEFAULT_COLLECTION_TITLE) -> Path:
    return Path(default_output_dir(collection_title))


# Ingestion / query defaults
DEFAULT_DB_PATH = Path("lancedb_data")
DEFAULT_TABLE_NAME = "documents"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
