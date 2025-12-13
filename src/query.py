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
    collection_title: Optional[str] = None,
    top_k: int = 10,
) -> str:
    """
    Run a hybrid search (semantic + BM25) against the LanceDB table and return a
    markdown-friendly summary string.

    Args:
        query: User query text.
        db_path: Path to LanceDB storage.
        table_name: Table name to search.
        collection_title: Optional filter on collection/doc title column.
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

    if collection_title:
        safe_title = collection_title.replace("'", "''")
        search_builder = search_builder.where(f"collection_title = '{safe_title}'")

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

        lines.append(f'{idx}. **{title}**: "{snippet}" (Source: {source}{score_str})')

    return "\n".join(lines)


def main(
    query: str = typer.Argument(..., help="Query string for hybrid search."),
    collection_title: Optional[str] = typer.Option(
        None, "--collection-title", "-c", help="Optional collection title filter."
    ),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, "--db-path", "-d"),
    table_name: str = typer.Option(DEFAULT_TABLE_NAME, "--table-name", "-t"),
    top_k: int = typer.Option(5, "--top-k", "-k"),
):
    results_md = search(
        query=query,
        db_path=db_path,
        table_name=table_name,
        collection_title=collection_title,
        top_k=top_k,
    )

    print(results_md)


def list_libraries(
    db_path: Path = DEFAULT_DB_PATH, table_name: str = DEFAULT_TABLE_NAME
) -> list[str]:
    """
    Return sorted unique non-null collection titles (libraries) from the table.
    """
    db = lancedb.connect(str(db_path))
    table = db.open_table(table_name)
    df = table.to_pandas()

    if "collection_title" not in df.columns:
        return []

    collections = df["collection_title"].dropna().unique().tolist()
    return sorted(collections)


if __name__ == "__main__":
    typer.run(main)
