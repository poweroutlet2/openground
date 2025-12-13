import asyncio
from pathlib import Path
from typing import Optional

import typer

from src.config import (
    CONCURRENCY_LIMIT,
    DEFAULT_LIBRARY_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_RAW_DATA_DIR,
    DEFAULT_TABLE_NAME,
    FILTER_KEYWORDS,
    SITEMAP_URL,
    get_raw_data_dir,
)

app = typer.Typer(help="Unified CLI for extraction, ingestion, and querying.")


@app.command()
def extract(
    sitemap_url: str = typer.Option(
        SITEMAP_URL, "--sitemap-url", "-s", help="Root sitemap URL to crawl."
    ),
    library_name: str = typer.Option(
        DEFAULT_LIBRARY_NAME,
        "--library-name",
        "-l",
        help="Name of the library/framework for this documentation.",
    ),
    filter_keywords: list[str] = typer.Option(
        FILTER_KEYWORDS,
        "--filter-keyword",
        "-f",
        help="Keyword filter applied to sitemap URLs. Can be specified multiple times (e.g., -f docs -f blog).",
        show_default=True,
    ),
    concurrency_limit: int = typer.Option(
        CONCURRENCY_LIMIT,
        "--concurrency-limit",
        "-c",
        help="Maximum number of concurrent requests.",
        min=1,
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Recommended to keep default. Directory for extracted JSON files (defaults to raw_data/{library_name}).",
    ),
):
    """Run the extraction pipeline to fetch and parse pages from a sitemap."""

    from src.extract import main as extract_main

    # If output_dir is not specified, construct it from library_name
    if output_dir is None:
        output_dir = str(get_raw_data_dir(library_name))

    async def _run():
        await extract_main(
            sitemap_url=sitemap_url,
            concurrency_limit=concurrency_limit,
            library_name=library_name,
            output_dir=output_dir,
            filter_keywords=filter_keywords,
        )

    asyncio.run(_run())


@app.command()
def ingest(
    library: Optional[str] = typer.Option(
        None,
        "--library",
        "-l",
        help="Library name to ingest from raw_data/{library}. Takes precedence over --data-dir.",
    ),
    data_dir: Path = typer.Option(
        DEFAULT_RAW_DATA_DIR,
        "--data-dir",
        "-d",
        help="Recommended to keep default. Directory containing parsed page files.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        "-b",
        help="Recommended to keep default. Directory for LanceDB storage.",
    ),
    table_name: str = typer.Option(
        DEFAULT_TABLE_NAME,
        "--table-name",
        "-t",
        help="Recommended to keep default. LanceDB table name.",
    ),
    batch_size: int = typer.Option(
        32,
        "--batch-size",
        "-bs",
        help="Recommended to keep default. Batch size for embedding generation.",
        min=1,
    ),
    chunk_size: int = typer.Option(
        1000,
        "--chunk-size",
        "-cs",
        help="Recommended to keep default. Chunk size for splitting documents.",
        min=1,
    ),
    chunk_overlap: int = typer.Option(
        200,
        "--chunk-overlap",
        "-co",
        help="Recommended to keep default. Overlap size between chunks.",
        min=0,
    ),
):
    """Chunk documents, generate embeddings, and ingest into LanceDB."""
    from src.ingest import ingest_to_lancedb, load_parsed_pages

    # If library is specified, construct the path and validate it exists
    if library:
        data_dir = get_raw_data_dir(library)
        if not data_dir.exists():
            raise typer.BadParameter(
                f"Library '{library}' not found at {data_dir}. "
                f"Use 'list-raw-libraries' to see available libraries."
            )

    pages = load_parsed_pages(data_dir)
    ingest_to_lancedb(
        pages=pages,
        db_path=db_path,
        table_name=table_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        batch_size=batch_size,
    )


@app.command("extract-and-ingest")
def extract_and_ingest(
    library_name: str = typer.Option(
        ..., "--library-name", "-l", help="Name of the library/framework."
    ),
    sitemap_url: str = typer.Option(
        ..., "--sitemap-url", "-s", help="Root sitemap URL to crawl."
    ),
    filter_keywords: list[str] = typer.Option(
        [],
        "--filter-keyword",
        "-f",
        help="Keyword filter applied to sitemap URLs. Can be specified multiple times (e.g., -f docs -f blog).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt between extract and ingest.",
    ),
):
    """Extract pages from a sitemap and ingest them into LanceDB in one step."""
    from src.extract import main as extract_main
    from src.ingest import ingest_to_lancedb, load_parsed_pages

    # Construct output directory from library_name
    output_dir = str(get_raw_data_dir(library_name))

    async def _run_extract():
        await extract_main(
            sitemap_url=sitemap_url,
            concurrency_limit=CONCURRENCY_LIMIT,
            library_name=library_name,
            output_dir=output_dir,
            filter_keywords=filter_keywords,
        )

    asyncio.run(_run_extract())

    data_dir = get_raw_data_dir(library_name)
    if not data_dir.exists():
        raise typer.BadParameter(
            f"Extraction completed but data directory not found at {data_dir}."
        )

    json_files = list(data_dir.glob("*.json"))
    page_count = len(json_files)
    print(f"\n✅ Extraction complete: {page_count} pages extracted to {data_dir}")

    if not yes:
        print("\nPress Enter to continue with ingestion, or Ctrl+C to exit...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n❌ Cancelled by user.")
            raise typer.Abort()

    print("\n🚀 Starting ingestion...")
    pages = load_parsed_pages(data_dir)
    ingest_to_lancedb(
        pages=pages,
        db_path=DEFAULT_DB_PATH,
        table_name=DEFAULT_TABLE_NAME,
        chunk_size=1000,
        chunk_overlap=200,
        batch_size=32,
    )


@app.command("query")
def query_cmd(
    query: str = typer.Argument(..., help="Query string for hybrid search."),
    library_name: Optional[str] = typer.Option(
        None,
        "--library-name",
        "-l",
        help="Optional library name filter.",
    ),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", "-d"),
    table_name: str = typer.Option(DEFAULT_TABLE_NAME, "--table-name", "-t"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to return."),
):
    """Run a hybrid search (semantic + BM25) against the LanceDB table."""
    from src.query import search

    results_md = search(
        query=query,
        db_path=db_path,
        table_name=table_name,
        library_name=library_name,
        top_k=top_k,
    )
    print(results_md)


@app.command("list-libraries")
def list_libraries_cmd(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", "-d"),
    table_name: str = typer.Option(DEFAULT_TABLE_NAME, "--table-name", "-t"),
):
    """List available libraries stored in LanceDB."""
    from src.query import list_libraries

    libraries = list_libraries(db_path=db_path, table_name=table_name)
    if not libraries:
        print("No libraries found.")
        return

    for lib in libraries:
        print(lib)


@app.command("list-raw-libraries")
def list_raw_libraries_cmd():
    """List available libraries in the raw_data directory."""
    raw_data_dir = Path("raw_data")
    if not raw_data_dir.exists():
        print(f"Directory {raw_data_dir} does not exist.")
        return

    libraries = [d.name for d in raw_data_dir.iterdir() if d.is_dir()]
    if not libraries:
        print(f"No libraries found in {raw_data_dir}.")
        return

    print("Available libraries in raw_data:")
    for lib in sorted(libraries):
        print(f"  - {lib}")


@app.command("install-mcp")
def install_mcp_cmd(
    wsl: bool = typer.Option(
        False,
        "--wsl",
        help="Generate WSL-compatible configuration (uses wsl.exe wrapper).",
    ),
):
    """Generate MCP server configuration JSON for agents."""
    import json

    # Auto-detect the project directory
    project_dir = Path(__file__).resolve().parent.parent

    if wsl:
        # For WSL, convert path to ~/... format if it's in home directory
        home = Path.home()
        if project_dir.is_relative_to(home):
            relative_path = project_dir.relative_to(home)
            wsl_path = f"~/{relative_path}"
        else:
            wsl_path = str(project_dir)

        config = {
            "mcpServers": {
                "openground": {
                    "command": "wsl.exe",
                    "args": [
                        "zsh",
                        "-c",
                        "-i",
                        f"cd {wsl_path} && uv run python src/server.py",
                    ],
                }
            }
        }
    else:
        config = {
            "mcpServers": {
                "openground": {
                    "command": "uv",
                    "args": ["run", "python", "src/server.py"],
                    "cwd": str(project_dir),
                }
            }
        }

    json_str = json.dumps(config, indent=2)

    # Build ASCII box
    title = " MCP Configuration "
    lines = json_str.split("\n")
    box_width = max(max(len(line) for line in lines), len(title)) + 4

    # Borders
    side_len = (box_width - len(title)) // 2
    top_border = "-" * side_len + title + "-" * side_len
    if len(top_border) < box_width:
        top_border += "-"
    bottom_border = "-" * len(top_border)

    # Print the box
    print()
    print(top_border)
    print()
    print(json_str)
    print()
    print(bottom_border)

    # Instructions
    print()
    print("Copy the JSON above into your MCP configuration file:")
    print("  Cursor:      ~/.cursor/mcp.json")
    print("  Claude Code: ~/Library/Application Support/Claude Code/config/mcp.json")
    print()


if __name__ == "__main__":
    app()
