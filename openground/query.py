import json
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    import lancedb
    import lancedb.table

from openground.config import DEFAULT_DB_PATH, DEFAULT_TABLE_NAME
from openground.embeddings import generate_embeddings

# Caches for database connection and table
_db_cache: dict[str, Any] = {}
_table_cache: dict[tuple[str, str], Any] = {}
_metadata_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _get_db(db_path: Path) -> "lancedb.DBConnection":
    """Get a cached database connection."""
    import lancedb

    path_str = str(db_path)
    if path_str not in _db_cache:
        _db_cache[path_str] = lancedb.connect(path_str)
    return _db_cache[path_str]


def _get_table(db_path: Path, table_name: str) -> Optional["lancedb.table.Table"]:
    """Get a cached table handle."""
    cache_key = (str(db_path), table_name)
    if cache_key not in _table_cache:
        db = _get_db(db_path)
        if table_name not in db.table_names():
            return None
        _table_cache[cache_key] = db.open_table(table_name)
    return _table_cache[cache_key]


def clear_query_caches():
    """Clear all query-related caches."""
    _db_cache.clear()
    _table_cache.clear()
    _metadata_cache.clear()


def _escape_sql_string(value: str) -> str:
    """
    Escape a string value for safe use in LanceDB SQL WHERE clauses.

    This function escapes single quotes and backslashes to prevent SQL injection.
    Note: LanceDB uses DataFusion which parses SQL, so proper escaping is critical.

    Args:
        value: The string value to escape

    Returns:
        Escaped string safe for use in SQL string literals
    """
    # Remove null bytes (can cause string truncation in some parsers)
    value = value.replace("\x00", "")
    # Escape backslashes first (must be done before escaping quotes)
    value = value.replace("\\", "\\\\")
    # Escape single quotes (SQL standard: ' becomes '')
    value = value.replace("'", "''")
    return value


def search(
    query: str,
    version: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
    library_name: Optional[str] = None,
    top_k: int = 10,
    show_progress: bool = True,
) -> str:
    """
    Run a hybrid search (semantic + BM25) against the LanceDB table and return a
    markdown-friendly summary string.

    Args:
        query: User query text.
        version: Version to filter results by.
        db_path: Path to LanceDB storage.
        table_name: Table name to search.
        library_name: Optional filter on library name column.
        top_k: Number of results to return.
        show_progress: Whether to show progress during embedding.
    """
    table = _get_table(db_path, table_name)
    if table is None:
        return "Found 0 matches."

    query_vec = generate_embeddings([query], show_progress=show_progress)[0]

    search_builder = table.search(query_type="hybrid").text(query).vector(query_vec)

    safe_version = _escape_sql_string(version)
    search_builder = search_builder.where(f"version = '{safe_version}'")

    if library_name:
        safe_name = _escape_sql_string(library_name)
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
        item_version = item.get("version") or version
        score = item.get("_distance") or item.get("_score")

        score_str = ""
        if isinstance(score, (int, float)):
            score_str = f", score={score:.4f}"
        elif score:
            score_str = f", score={score}"

        # Embed tool call hint for fetching full content
        tool_hint = json.dumps(
            {"tool": "get_full_content", "url": source, "version": item_version}
        )

        lines.append(
            f'{idx}. **{title}**: "{snippet}" (Source: {source}, Version: {item_version}{score_str})\n'
            f"   To get full page content: {tool_hint}"
        )

    return "\n".join(lines)


def list_libraries(
    db_path: Path = DEFAULT_DB_PATH, table_name: str = DEFAULT_TABLE_NAME
) -> list[str]:
    """
    Return sorted unique non-null library names from the table.
    """
    libs_with_versions = list_libraries_with_versions(
        db_path=db_path, table_name=table_name
    )
    return sorted(libs_with_versions.keys())


def list_libraries_with_versions(
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
    search_term: Optional[str] = None,
) -> dict[str, list[str]]:
    """
    Return a dictionary mapping library names to their sorted version lists.

    Args:
        db_path: Path to LanceDB storage.
        table_name: Table name to search.
        search_term: Optional search term to filter library names (case-insensitive).

    Returns:
        Dictionary mapping library names to sorted lists of versions.
        Returns empty dict if no libraries found or table doesn't exist.
    """
    cache_key = (str(db_path), table_name)
    if cache_key in _metadata_cache:
        result = _metadata_cache[cache_key]
    else:
        table = _get_table(db_path, table_name)
        if table is None:
            return {}

        # Load unique pairs efficiently
        df = (
            table.search()
            .select(["library_name", "version"])
            .to_pandas()
            .drop_duplicates()
            .dropna()
        )

        # Group by library name and collect unique versions
        result = {}
        for _, row in df.iterrows():
            lib_name = row["library_name"]
            version = row["version"]
            if lib_name not in result:
                result[lib_name] = []
            if version not in result[lib_name]:
                result[lib_name].append(version)

        for lib_name in result:
            result[lib_name] = sorted(result[lib_name])

        # Cache the full results
        _metadata_cache[cache_key] = result

    if search_term:
        term_lower = search_term.lower()
        result = {
            lib_name: versions
            for lib_name, versions in result.items()
            if term_lower in lib_name.lower()
        }

    return dict(sorted(result.items()))


def get_full_content(
    url: str,
    version: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> str:
    """
    Retrieve the full content of a document by its URL and version.

    Args:
        url: URL of the document to retrieve.
        version: Version of the document to retrieve.
        db_path: Path to LanceDB storage.
        table_name: Table name to search.

    Returns:
        Formatted markdown string with title, source URL, and full content.
    """
    table = _get_table(db_path, table_name)
    if table is None:
        return f"No content found for URL: {url}"

    # Query all chunks for this URL and version
    safe_url = _escape_sql_string(url)
    safe_version = _escape_sql_string(version)
    df = (
        table.search()
        .where(f"url = '{safe_url}' AND version = '{safe_version}'")
        .select(["title", "content", "chunk_index"])
        .to_pandas()
    )

    if df.empty:
        return f"No content found for URL: {url} (version: {version})"

    # Sort by chunk_index and concatenate content
    df = df.sort_values("chunk_index")
    full_content = "\n\n".join(df["content"].tolist())

    title = df.iloc[0].get("title", "(no title)")
    return f"# {title}\n\nSource: {url}\nVersion: {version}\n\n{full_content}"


def get_library_stats(
    library_name: str,
    version: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> dict | None:
    """Get statistics for a library version (chunk count, unique URLs, etc.)."""
    table = _get_table(db_path, table_name)
    if table is None:
        return None

    safe_name = _escape_sql_string(library_name)
    safe_version = _escape_sql_string(version)
    filter_str = f"library_name = '{safe_name}' AND version = '{safe_version}'"

    # Use count_rows for chunk count
    chunk_count = table.count_rows(filter=filter_str)
    if chunk_count == 0:
        return None

    # Get sample titles and unique URL count more efficiently
    # We only need a few titles, so we can limit the search
    df_titles = (
        table.search().where(filter_str).select(["title", "url"]).limit(500).to_pandas()
    )

    titles = [t for t in df_titles["title"].unique().tolist() if t and str(t).strip()][
        :5
    ]

    unique_urls = df_titles["url"].nunique()
    if chunk_count > 500:
        # If there are more chunks, unique_urls might be higher than our sample
        # For now, we'll just note it's at least this many, or we can load all URLs
        # which is usually okay as URLs are small strings.
        df_all_urls = table.search().where(filter_str).select(["url"]).to_pandas()
        unique_urls = df_all_urls["url"].nunique()

    return {
        "library_name": library_name,
        "version": version,
        "chunk_count": chunk_count,
        "unique_urls": unique_urls,
        "titles": titles,
    }


def delete_library(
    library_name: str,
    version: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> int:
    """Delete all documents for a library version. Returns count of deleted rows."""
    table = _get_table(db_path, table_name)
    if table is None:
        return 0

    safe_name = _escape_sql_string(library_name)
    safe_version = _escape_sql_string(version)

    # Get count before deletion
    count = table.count_rows(
        filter=f"library_name = '{safe_name}' AND version = '{safe_version}'"
    )

    # Delete rows
    table.delete(f"library_name = '{safe_name}' AND version = '{safe_version}'")
    return count


def delete_urls(
    urls: list[str],
    library_name: str,
    version: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> int:
    """
    Delete all chunks for given URLs from LanceDB.

    Args:
        urls: List of URLs to delete
        library_name: Library name filter
        version: Version filter
        db_path: Path to LanceDB storage
        table_name: Table name

    Returns:
        Number of deleted rows
    """
    table = _get_table(db_path, table_name)
    if table is None:
        return 0

    if not urls:
        return 0

    safe_name = _escape_sql_string(library_name)
    safe_version = _escape_sql_string(version)

    # Build WHERE clause with OR conditions for URLs to delete
    safe_urls = [_escape_sql_string(url) for url in urls]
    url_conditions = " OR ".join(f"url = '{url}'" for url in safe_urls)
    filter_str = f"library_name = '{safe_name}' AND version = '{safe_version}' AND ({url_conditions})"

    count = table.count_rows(filter=filter_str)

    table.delete(filter_str)
    return count


def library_version_exists(
    library_name: str,
    version: str,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> bool:
    """
    Check if library version exists in LanceDB.

    Args:
        library_name: Library name to check
        version: Version to check
        db_path: Path to LanceDB storage
        table_name: Table name

    Returns:
        True if library version exists, False otherwise
    """
    stats = get_library_stats(library_name, version, db_path, table_name)
    return stats is not None
