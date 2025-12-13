import json
from pathlib import Path
from collections.abc import Iterable

import lancedb
import pyarrow as pa
import torch
import typer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.extract import ParsedPage
from src.config import (
    DEFAULT_DB_PATH,
    DEFAULT_RAW_DATA_DIR,
    DEFAULT_TABLE_NAME,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)


def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(device: str) -> SentenceTransformer:
    model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    return model


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
                title=raw.get("title"),
                description=raw.get("description"),
                last_modified=raw.get("last_modified"),
                content=raw.get("content", ""),
            )
        )

    return pages


def chunk_document(page: ParsedPage, chunk_size: int, chunk_overlap: int) -> list[dict]:
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
                "title": page["title"] or "",
                "description": page["description"] or "",
                "last_modified": page["last_modified"] or "",
                "content": chunk,
                "chunk_index": idx,
            }
        )
    return records


def generate_embeddings(
    texts: Iterable[str], model: SentenceTransformer, batch_size: int
) -> list[list[float]]:
    texts_list = list(texts)
    all_embeddings = []

    with tqdm(
        total=len(texts_list),
        desc="Generating embeddings",
        unit="text",
        unit_scale=True,
    ) as pbar:
        for i in range(0, len(texts_list), batch_size):
            batch = texts_list[i : i + batch_size]
            batch_embeddings = model.encode(
                batch,
                batch_size=len(batch),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,  # We use our own progress bar
            )
            all_embeddings.extend(batch_embeddings.tolist())
            pbar.update(len(batch))

    return all_embeddings


def ensure_table(db, table_name: str):
    if table_name in db.table_names():
        return db.open_table(table_name)
    schema = pa.schema(
        [
            pa.field("url", pa.string()),
            pa.field("library_name", pa.string()),
            pa.field("title", pa.string()),
            pa.field("description", pa.string()),
            pa.field("last_modified", pa.string()),
            pa.field("content", pa.string()),
            pa.field("chunk_index", pa.int64()),
            pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIMENSIONS)),
        ]
    )
    return db.create_table(table_name, data=[], mode="create", schema=schema)


def ingest_to_lancedb(
    pages: list[ParsedPage],
    db_path: Path,
    table_name: str,
    chunk_size: int,
    chunk_overlap: int,
    batch_size: int,
):
    if not pages:
        print("No pages to ingest.")
        return

    device = get_device()
    print(f"Using device: {device}")
    model = load_model(device)

    db = lancedb.connect(str(db_path))
    table = ensure_table(db, table_name)

    # Chunk documents with progress
    all_records = []
    for page in tqdm(pages, desc="Chunking documents", unit="page"):
        all_records.extend(chunk_document(page, chunk_size, chunk_overlap))

    print(f"Prepared {len(all_records)} chunks from {len(pages)} pages.")

    if not all_records:
        print("No chunks produced; skipping ingestion.")
        return

    # Generate embeddings with progress
    content_texts = [rec["content"] for rec in all_records]
    embeddings = generate_embeddings(content_texts, model, batch_size)

    # Add embeddings to records
    for rec, emb in zip(all_records, embeddings):
        rec["vector"] = emb

    # Save to LanceDB with progress indication
    print(f"Inserting {len(all_records)} chunks into LanceDB...")
    table.add(all_records)

    # Create FTS index
    print("Creating full-text search index...")
    try:
        table.create_fts_index("content", replace=True)
        print("✅ Full-text search index created")
    except Exception as exc:  # best-effort; index may already exist
        print(f"FTS index creation skipped: {exc}")

    print(f"🎉 Ingested {len(all_records)} chunks into table '{table_name}'.")


def main(
    data_dir: Path = typer.Option(
        DEFAULT_RAW_DATA_DIR,
        "--data-dir",
        "-d",
        help="Directory containing parsed page files.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH, "--db-path", "-b", help="Directory for LanceDB storage."
    ),
    table_name: str = typer.Option(
        DEFAULT_TABLE_NAME, "--table-name", "-t", help="LanceDB table name."
    ),
    chunk_size: int = typer.Option(
        1000, "--chunk-size", "-c", help="Chunk size for splitting documents."
    ),
    chunk_overlap: int = typer.Option(
        200, "--chunk-overlap", "-o", help="Overlap size between chunks."
    ),
    batch_size: int = typer.Option(
        32, "--batch-size", "-bs", help="Batch size for embedding generation."
    ),
):
    pages = load_parsed_pages(data_dir)
    ingest_to_lancedb(
        pages=pages,
        db_path=db_path,
        table_name=table_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        batch_size=batch_size,
    )


if __name__ == "__main__":
    typer.run(main)
