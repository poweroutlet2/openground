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
    EMBEDDING_DIMENSIONS,
    get_effective_config,
)
from openground.console import success
from openground.embeddings import generate_embeddings


def load_parsed_pages(directory: Path) -> list[ParsedPage]:
    pages: list[ParsedPage] = []
    if not directory.exists():
        raise FileNotFoundError(f"Data directory not found: {directory}")

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
    chunk_size = config["ingestion"]["chunk_size"]
    chunk_overlap = config["ingestion"]["chunk_overlap"]

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


def ensure_table(
    db: DBConnection, table_name: str, embedding_dimensions: int = EMBEDDING_DIMENSIONS
) -> Table:
    if table_name in db.table_names():
        return db.open_table(table_name)
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
        ]
    )
    return db.create_table(table_name, data=[], mode="create", schema=schema)


def ingest_to_lancedb(
    pages: list[ParsedPage],
) -> None:
    if not pages:
        print("No pages to ingest.")
        return

    # Chunk documents with progress
    all_records = []
    for page in tqdm(pages, desc="Chunking documents", unit="page"):
        all_records.extend(chunk_document(page))

    print(f"Prepared {len(all_records)} chunks from {len(pages)} pages.")

    if not all_records:
        print("No chunks produced; skipping ingestion.")
        return

    # Generate embeddings with progress
    content_texts = [rec["content"] for rec in all_records]
    embeddings = generate_embeddings(content_texts)

    # Add embeddings to records
    for rec, emb in zip(all_records, embeddings):
        rec["vector"] = emb

    config = get_effective_config()
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]
    embedding_dimensions = config["ingestion"]["embedding_dimensions"]

    db = lancedb.connect(str(db_path))
    table = ensure_table(db, table_name, embedding_dimensions=embedding_dimensions)

    # Save to LanceDB with progress indication
    print(f"Inserting {len(all_records)} chunks into LanceDB...")
    table.add(all_records)

    # Create FTS index
    print("Creating full-text search index...")
    try:
        table.create_fts_index("content", replace=True)
        success("Full-text search index created")
    except Exception as exc:  # best-effort; index may already exist
        print(f"FTS index creation skipped: {exc}")

    success(f"Ingested {len(all_records)} chunks into table '{table_name}'.")
