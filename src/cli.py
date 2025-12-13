import asyncio
from pathlib import Path
from typing import Optional

import typer

from src.extract import (
    COLLECTION_TITLE as EXTRACT_COLLECTION_TITLE,
    CONCURRENCY_LIMIT,
    FILTER_KEYWORDS,
    OUTPUT_DIR,
    SITEMAP_URL,
    main as extract_main,
)
from src.ingest import (
    DEFAULT_DB_PATH,
    DEFAULT_TABLE_NAME,
    RAW_DATA_DIR,
    ingest_to_lancedb,
    load_parsed_pages,
)
from src.query import list_libraries, search

app = typer.Typer(help="Unified CLI for extraction, ingestion, and querying.")


@app.command()
def extract(
    sitemap_url: str = typer.Option(
        SITEMAP_URL, "--sitemap-url", "-s", help="Root sitemap URL to crawl."
    ),
    concurrency_limit: int = typer.Option(
        CONCURRENCY_LIMIT,
        "--concurrency-limit",
        "-c",
        help="Maximum number of concurrent requests.",
        min=1,
    ),
    collection_title: str = typer.Option(
        EXTRACT_COLLECTION_TITLE,
        "--collection-title",
        "-t",
        help="Label to store with the extracted documents.",
    ),
    output_dir: str = typer.Option(
        OUTPUT_DIR,
        "--output-dir",
        "-o",
        help="Directory for extracted JSON files (defaults to raw_data/docs/{collection_title}).",
    ),
    filter_keywords: list[str] = typer.Option(
        FILTER_KEYWORDS,
        "--filter-keyword",
        "-f",
        help="Keyword filter applied to sitemap URLs. Can be specified multiple times (e.g., -f docs -f blog).",
        show_default=True,
    ),
):
    """Run the extraction pipeline to fetch and parse pages from a sitemap."""

    async def _run():
        await extract_main(
            sitemap_url=sitemap_url,
            concurrency_limit=concurrency_limit,
            collection_title=collection_title,
            output_dir=output_dir,
            filter_keywords=filter_keywords,
        )

    asyncio.run(_run())


@app.command()
def ingest(
    data_dir: Path = typer.Option(
        RAW_DATA_DIR, "--data-dir", "-d", help="Directory containing parsed page files."
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH, "--db-path", "-b", help="Directory for LanceDB storage."
    ),
    table_name: str = typer.Option(
        DEFAULT_TABLE_NAME, "--table-name", "-t", help="LanceDB table name."
    ),
    chunk_size: int = typer.Option(
        1000, "--chunk-size", "-cs", help="Chunk size for splitting documents.", min=1
    ),
    chunk_overlap: int = typer.Option(
        200,
        "--chunk-overlap",
        "-co",
        help="Overlap size between chunks.",
        min=0,
    ),
    batch_size: int = typer.Option(
        32, "--batch-size", "-bs", help="Batch size for embedding generation.", min=1
    ),
):
    """Chunk documents, generate embeddings, and ingest into LanceDB."""
    pages = load_parsed_pages(data_dir)
    ingest_to_lancedb(
        pages=pages,
        db_path=db_path,
        table_name=table_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        batch_size=batch_size,
    )


@app.command("query")
def query_cmd(
    query: str = typer.Argument(..., help="Query string for hybrid search."),
    collection_title: Optional[str] = typer.Option(
        None,
        "--collection-title",
        "-c",
        help="Optional collection title filter.",
    ),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", "-d"),
    table_name: str = typer.Option(DEFAULT_TABLE_NAME, "--table-name", "-t"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to return."),
):
    """Run a hybrid search (semantic + BM25) against the LanceDB table."""
    results_md = search(
        query=query,
        db_path=db_path,
        table_name=table_name,
        collection_title=collection_title,
        top_k=top_k,
    )
    print(results_md)


@app.command("list-libraries")
def list_libraries_cmd(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", "-d"),
    table_name: str = typer.Option(DEFAULT_TABLE_NAME, "--table-name", "-t"),
):
    """List available libraries (collection titles) stored in LanceDB."""
    libraries = list_libraries(db_path=db_path, table_name=table_name)
    if not libraries:
        print("No libraries found.")
        return

    for lib in libraries:
        print(lib)


if __name__ == "__main__":
    app()
