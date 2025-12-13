import json
from pathlib import Path
from typing import Optional

import lancedb
import typer
from sentence_transformers import SentenceTransformer

from src.config import DEFAULT_DB_PATH, DEFAULT_TABLE_NAME
from src.ingest import get_device, load_model

# Cache the model so repeated queries avoid reloading
_MODEL_CACHE: Optional[SentenceTransformer] = None
_DEVICE_CACHE: Optional[str] = None


def _get_model() -> tuple[SentenceTransformer, str]:
    global _MODEL_CACHE, _DEVICE_CACHE
    if _MODEL_CACHE is None:
        device = get_device()
        _DEVICE_CACHE = device
        _MODEL_CACHE = load_model(device)
    return _MODEL_CACHE, _DEVICE_CACHE or get_device()


def _embed_query(model: SentenceTransformer, query: str) -> list[float]:
    vec = model.encode(
        [query],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )[0]
    return vec.tolist()


def search(
    query: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
    library_name: Optional[str] = None,
    top_k: int = 10,
) -> str:
    """
    Run a hybrid search (semantic + BM25) against the LanceDB table and return a
    markdown-friendly summary string.

    Args:
        query: User query text.
        db_path: Path to LanceDB storage.
        table_name: Table name to search.
        library_name: Optional filter on library name column.
        top_k: Number of results to return.
    """
    model, _device = _get_model()
    db = lancedb.connect(str(db_path))
    table = db.open_table(table_name)

    query_vec = _embed_query(model, query)

    search_builder = (
        table.search(query_type="hybrid")
        .text(query)  # BM25 / full-text side
        .vector(query_vec)  # Semantic side
    )

    if library_name:
        safe_name = library_name.replace("'", "''")
        search_builder = search_builder.where(f"library_name = '{safe_name}'")

    results = search_builder.limit(top_k).to_list()

    if not results:
        return "Found 0 matches."

    lines = [f"Found {len(results)} match{'es' if len(results) != 1 else ''}."]
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "(no title)"
        # Return the full chunk so downstream consumers (LLM) see the whole text.
        snippet = (item.get("content") or "").strip()
        source = item.get("url") or "unknown"
        score = item.get("_distance") or item.get("_score")

        score_str = ""
        if isinstance(score, (int, float)):
            score_str = f", score={score:.4f}"
        elif score:
            score_str = f", score={score}"

        # Embed tool call hint for fetching full content
        tool_hint = json.dumps({"tool": "get_full_content", "url": source})

        lines.append(
            f'{idx}. **{title}**: "{snippet}" (Source: {source}{score_str})\n'
            f"   To get full page content: {tool_hint}"
        )

    return "\n".join(lines)


def main(
    query: str = typer.Argument(..., help="Query string for hybrid search."),
    library_name: Optional[str] = typer.Option(
        None, "--library-name", "-l", help="Optional library name filter."
    ),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", "-d"),
    table_name: str = typer.Option(DEFAULT_TABLE_NAME, "--table-name", "-t"),
    top_k: int = typer.Option(5, "--top-k", "-k"),
):
    results_md = search(
        query=query,
        db_path=db_path,
        table_name=table_name,
        library_name=library_name,
        top_k=top_k,
    )

    print(results_md)


def list_libraries(
    db_path: Path = DEFAULT_DB_PATH, table_name: str = DEFAULT_TABLE_NAME
) -> list[str]:
    """
    Return sorted unique non-null library names from the table.
    """
    db = lancedb.connect(str(db_path))
    table = db.open_table(table_name)
    df = table.to_pandas()

    libraries = df["library_name"].dropna().unique().tolist()
    return sorted(libraries)


def search_libraries(
    search_term: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> list[str]:
    """
    Return sorted unique library names that contain the search term (case-insensitive).
    Returns a list with a message if no libraries match.
    """
    libraries = list_libraries(db_path=db_path, table_name=table_name)
    term_lower = search_term.lower()
    filtered = [lib for lib in libraries if term_lower in lib.lower()]
    if not filtered:
        return [f"No libraries found matching '{search_term}'."]
    return filtered


def get_full_content(
    url: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> str:
    """
    Retrieve the full content of a document by its URL.

    Args:
        url: URL of the document to retrieve.
        db_path: Path to LanceDB storage.
        table_name: Table name to search.

    Returns:
        Formatted markdown string with title, source URL, and full content.
    """
    db = lancedb.connect(str(db_path))
    table = db.open_table(table_name)

    # Query all chunks for this URL
    safe_url = url.replace("'", "''")
    df = table.search().where(f"url = '{safe_url}'").to_pandas()

    if df.empty:
        return f"No content found for URL: {url}"

    # Sort by chunk_index and concatenate content
    df = df.sort_values("chunk_index")
    full_content = "\n\n".join(df["content"].tolist())

    title = df.iloc[0].get("title", "(no title)")
    return f"# {title}\n\nSource: {url}\n\n{full_content}"


if __name__ == "__main__":
    typer.run(main)
