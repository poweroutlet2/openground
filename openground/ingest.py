import json
from pathlib import Path

import lancedb
import pyarrow as pa
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

from openground.config import TABLE_NAME, get_settings
from openground.embeddings import generate_embeddings
from openground.extract.common import ParsedPage


def load_parsed_pages(directory: Path) -> list[ParsedPage]:
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


def chunk_document(page: ParsedPage) -> list[dict]:
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    chunks = splitter.split_text(page["content"])
    return [
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
        for idx, chunk in enumerate(chunks)
    ]


def ensure_table(db) -> "lancedb.table.Table":
    if TABLE_NAME in db.table_names():
        return db.open_table(TABLE_NAME)

    settings = get_settings()
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
            pa.field("vector", pa.list_(pa.float32(), settings.embedding_dimensions)),
        ],
        metadata={
            "embedding_backend": settings.embedding_backend,
            "embedding_model": settings.embedding_model,
        },
    )
    return db.create_table(TABLE_NAME, data=[], mode="create", schema=schema)


def ingest_pages(pages: list[ParsedPage]) -> None:
    """Chunk pages, embed them, and insert into LanceDB."""
    if not pages:
        print("No pages to ingest.")
        return

    db = lancedb.connect(str(get_settings().db_path))
    table = ensure_table(db)

    all_records = []
    for page in tqdm(pages, desc="Chunking documents", unit="page"):
        all_records.extend(chunk_document(page))

    if not all_records:
        print("No chunks produced; skipping ingestion.")
        return

    embeddings = generate_embeddings([rec["content"] for rec in all_records])
    for rec, emb in zip(all_records, embeddings):
        rec["vector"] = emb

    print(f"Inserting {len(all_records)} chunks into LanceDB...")
    table.add(all_records)

    try:
        table.create_fts_index("content", replace=True)
    except Exception as exc:  # best-effort; index may already exist
        print(f"FTS index creation skipped: {exc}")
