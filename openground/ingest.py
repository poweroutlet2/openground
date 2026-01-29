from lancedb import Table
from lancedb.db import DBConnection
import json
from pathlib import Path

import lancedb
import pyarrow as pa
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

from openground.extract.common import ParsedPage
from openground.config import (
    get_effective_config,
)
from openground.console import success
from openground.embeddings import generate_embeddings


def load_parsed_pages(directory: Path) -> list[ParsedPage]:
    """
    Load parsed pages from a directory.

    Args:
        directory: Path to the directory containing JSON files

    Returns:
        List of parsed pages.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Data directory not found: {directory}")

    pages: list[ParsedPage] = []
    for path in sorted(list(directory.glob("*.md")) + list(directory.glob("*.json"))):
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        pages.append(
            ParsedPage(
                url=raw.get("url", ""),
                library_name=raw.get("library_name", ""),
                version=raw.get("version", "latest"),
                title=raw.get("title"),
                description=raw.get("description"),
                last_modified=raw.get("last_modified"),
                content=raw.get("content", ""),
            )
        )

    return pages


def chunk_document(
    page: ParsedPage,
) -> list[dict]:
    config = get_effective_config()
    chunk_size = config["embeddings"]["chunk_size"]
    chunk_overlap = config["embeddings"]["chunk_overlap"]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = splitter.split_text(page["content"])
    records = []
    for idx, chunk in enumerate(chunks):
        records.append(
            {
                "url": page["url"],
                "library_name": page["library_name"],
                "version": page["version"],
                "title": page["title"] or "",
                "description": page["description"] or "",
                "last_modified": page["last_modified"] or "",
                "content": chunk,
                "chunk_index": idx,
            }
        )
    return records


def _get_table_metadata(table: Table) -> dict | None:
    """Extract embedding metadata from table schema.

    Args:
        table: The LanceDB table to check.

    Returns:
        Dictionary with 'embedding_backend' and 'embedding_model' keys if metadata exists,
        None otherwise.
    """
    schema = table.schema
    if schema.metadata is None:
        raise ValueError("Table metadata not found")

    # PyArrow metadata is stored as bytes, need to decode both keys and values
    metadata_dict = {}
    for key, value in schema.metadata.items():
        # Decode key if it's bytes
        decoded_key = key.decode("utf-8") if isinstance(key, bytes) else key
        # Decode value if it's bytes
        decoded_value = value.decode("utf-8") if isinstance(value, bytes) else value
        metadata_dict[decoded_key] = decoded_value

    # Check if embedding metadata exists
    if "embedding_backend" in metadata_dict and "embedding_model" in metadata_dict:
        return {
            "embedding_backend": metadata_dict["embedding_backend"],
            "embedding_model": metadata_dict["embedding_model"],
        }
    return None


def _validate_table_metadata(table: Table, backend: str, model: str) -> None:
    """Validate that table metadata matches current embedding configuration.

    Args:
        table: The LanceDB table to validate.
        backend: Current embedding backend from config.
        model: Current embedding model from config.

    Raises:
        ValueError: If table metadata exists and doesn't match current config.
    """
    stored_metadata = _get_table_metadata(table)

    if stored_metadata is None:
        raise ValueError(f"Table metadata not found: {stored_metadata}")

    stored_backend = stored_metadata["embedding_backend"]
    stored_model = stored_metadata["embedding_model"]

    if stored_backend != backend or stored_model != model:
        raise ValueError(
            f"Embedding configuration mismatch detected!\n\n"
            f"This table was created with:\n"
            f"  Backend: {stored_backend}\n"
            f"  Model: {stored_model}\n\n"
            f"Current configuration is:\n"
            f"  Backend: {backend}\n"
            f"  Model: {model}\n\n"
            f"To resolve this, you can:\n"
            f"  1. Change your config to match the table's original settings\n"
            f"  2. Run `openground nuke embeddings` and then `openground embed`\n"
        )


def ensure_table(
    db: DBConnection,
    table_name: str,
    embedding_dimensions: int,
    embedding_backend: str,
    embedding_model: str,
) -> Table:
    if table_name in db.table_names():
        # Table exists - validate metadata matches current config
        table = db.open_table(table_name)
        _validate_table_metadata(table, embedding_backend, embedding_model)
        return table

    # Create new table with embedding metadata in schema
    metadata = {
        "embedding_backend": embedding_backend,
        "embedding_model": embedding_model,
    }
    schema = pa.schema(
        [
            pa.field("url", pa.string()),
            pa.field("library_name", pa.string()),
            pa.field("version", pa.string()),
            pa.field("title", pa.string()),
            pa.field("description", pa.string()),
            pa.field("last_modified", pa.string()),
            pa.field("content", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("vector", pa.list_(pa.float32(), embedding_dimensions)),
        ],
        metadata=metadata,
    )
    return db.create_table(table_name, data=[], mode="create", schema=schema)


def ingest_to_lancedb(
    pages: list[ParsedPage],
) -> None:
    if not pages:
        print("No pages to ingest.")
        return

    config = get_effective_config()
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]
    embedding_dimensions = config["embeddings"]["embedding_dimensions"]
    embedding_backend = config["embeddings"]["embedding_backend"]
    embedding_model = config["embeddings"]["embedding_model"]

    db = lancedb.connect(str(db_path))
    table = ensure_table(
        db,
        table_name,
        embedding_dimensions=embedding_dimensions,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
    )

    # Chunk documents with progress
    all_records = []
    for page in tqdm(pages, desc="Chunking documents", unit="page"):
        all_records.extend(chunk_document(page))

    if not all_records:
        print("No chunks produced; skipping ingestion.")
        return

    # Generate embeddings with progress
    content_texts = [rec["content"] for rec in all_records]
    embeddings = generate_embeddings(content_texts)

    # Add embeddings to records
    for rec, emb in zip(all_records, embeddings):
        rec["vector"] = emb

    print(f"Inserting {len(all_records)} chunks into LanceDB...")
    table.add(all_records)

    try:
        table.create_fts_index("content", replace=True)
    except Exception as exc:  # best-effort; index may already exist
        print(f"FTS index creation skipped: {exc}")


def ingest_pages_to_lancedb(
    pages: list[ParsedPage],
    db_path: Path,
    table_name: str,
) -> None:
    """
    Ingest specific pages to LanceDB with explicit db/table params.

    Similar to ingest_to_lancedb but allows override for update flow.

    Args:
        pages: List of parsed pages to ingest
        db_path: Path to LanceDB storage
        table_name: Name of the table to use
    """
    if not pages:
        print("No pages to ingest.")
        return

    config = get_effective_config()
    embedding_dimensions = config["embeddings"]["embedding_dimensions"]
    embedding_backend = config["embeddings"]["embedding_backend"]
    embedding_model = config["embeddings"]["embedding_model"]

    db = lancedb.connect(str(db_path))
    table = ensure_table(
        db,
        table_name,
        embedding_dimensions=embedding_dimensions,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
    )

    all_records = []
    for page in tqdm(pages, desc="Chunking documents", unit="page"):
        all_records.extend(chunk_document(page))

    if not all_records:
        print("No chunks produced; skipping ingestion.")
        return

    content_texts = [rec["content"] for rec in all_records]
    embeddings = generate_embeddings(content_texts)

    for rec, emb in zip(all_records, embeddings):
        rec["vector"] = emb

    print(f"Inserting {len(all_records)} chunks into LanceDB...")
    table.add(all_records)

    try:
        table.create_fts_index("content", replace=True)
    except Exception as exc:  # best-effort; index may already exist
        print(f"FTS index creation skipped: {exc}")
