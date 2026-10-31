import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import lancedb.table

from openground.config import TABLE_NAME, get_settings
from openground.console import UserError
from openground.embeddings import generate_embeddings


def _get_table() -> Optional["lancedb.table.Table"]:
    """Open the documents table fresh so other processes' writes are visible."""
    import lancedb

    db = lancedb.connect(str(get_settings().db_path))
    return db.open_table(TABLE_NAME) if TABLE_NAME in db.table_names() else None


def _escape_sql_string(value: str) -> str:
    """Escape a value for a single-quoted LanceDB (DataFusion) SQL literal."""
    value = value.replace("\x00", "")
    return value.replace("\\", "\\\\").replace("'", "''")


def _match(library_name: str, version: str) -> str:
    return (
        f"library_name = '{_escape_sql_string(library_name)}' "
        f"AND version = '{_escape_sql_string(version)}'"
    )


def check_embedding_config() -> None:
    """Fail if the stored embeddings were made with a different backend/model than configured."""
    table = _get_table()
    if table is None or not table.schema.metadata:
        return

    stored = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in table.schema.metadata.items()
    }
    settings = get_settings()
    current = (settings.embedding_backend, settings.embedding_model)
    if (stored.get("embedding_backend"), stored.get("embedding_model")) != current:
        raise UserError(
            "Embedding config mismatch.\n"
            f"  Stored:  {stored.get('embedding_backend')} / {stored.get('embedding_model')}\n"
            f"  Config:  {current[0]} / {current[1]}\n"
            "Set embedding_backend and embedding_model in config.json to the stored "
            "values (see `openground config`), or run `openground reset` and re-add "
            "your libraries."
        )


def check_library_version(library_name: str | None, version: str | None) -> None:
    """Raise a helpful UserError if the library/version filter matches nothing stored."""
    libraries = list_libraries_with_versions()
    if library_name is not None and library_name not in libraries:
        available = ", ".join(libraries) or "none (add one with `openground add`)"
        raise UserError(
            f"Library '{library_name}' not found. Available libraries: {available}"
        )
    if version is None:
        return

    if library_name is not None:
        versions = libraries[library_name]
    else:
        versions = sorted({v for vs in libraries.values() for v in vs})
    if version not in versions:
        scope = f" for library '{library_name}'" if library_name else ""
        raise UserError(
            f"Version '{version}' not found{scope}. "
            f"Available versions: {', '.join(versions) or 'none'}"
        )


def search(
    query: str,
    version: Optional[str] = None,
    library_name: Optional[str] = None,
    top_k: Optional[int] = None,
    show_progress: bool = True,
) -> str:
    """Hybrid (semantic + BM25) search; returns a markdown summary of the matches."""
    check_library_version(library_name, version)
    check_embedding_config()
    table = _get_table()
    if table is None:
        return "Found 0 matches."

    query_vec = generate_embeddings([query], show_progress=show_progress)[0]
    builder = table.search(query_type="hybrid").text(query).vector(query_vec)

    filters = []
    if version:
        filters.append(f"version = '{_escape_sql_string(version)}'")
    if library_name:
        filters.append(f"library_name = '{_escape_sql_string(library_name)}'")
    if filters:
        builder = builder.where(" AND ".join(filters))

    results = builder.limit(top_k or get_settings().top_k).to_list()
    if not results:
        return "Found 0 matches."

    lines = [f"Found {len(results)} match{'es' if len(results) != 1 else ''}."]
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "(no title)"
        snippet = (item.get("content") or "").strip()
        source = item.get("url") or "unknown"
        item_version = item.get("version") or version or "latest"
        score = item.get("_distance") or item.get("_score")

        score_str = ""
        if isinstance(score, (int, float)):
            score_str = f", score={score:.4f}"
        elif score:
            score_str = f", score={score}"

        tool_hint = json.dumps(
            {"tool": "get_full_content", "url": source, "version": item_version}
        )
        lines.append(
            f'{idx}. **{title}**: "{snippet}" (Source: {source}, Version: {item_version}{score_str})\n'
            f"   To get full page content: {tool_hint}"
        )

    return "\n".join(lines)


def list_libraries_with_versions() -> dict[str, list[str]]:
    """Map each stored library to its sorted versions (empty if nothing is stored)."""
    table = _get_table()
    if table is None:
        return {}

    df = (
        table.search()
        .select(["library_name", "version"])
        .to_pandas()
        .drop_duplicates()
        .dropna()
    )
    result: dict[str, list[str]] = {}
    for lib_name, version in zip(df["library_name"], df["version"]):
        result.setdefault(lib_name, []).append(version)
    return {name: sorted(versions) for name, versions in sorted(result.items())}


def get_full_content(url: str, version: str) -> str:
    """Return the full text of a stored page, reassembled from its chunks."""
    table = _get_table()
    if table is None:
        return f"No content found for URL: {url}"

    df = (
        table.search()
        .where(
            f"url = '{_escape_sql_string(url)}' "
            f"AND version = '{_escape_sql_string(version)}'"
        )
        .select(["title", "content", "chunk_index"])
        .to_pandas()
    )
    if df.empty:
        return f"No content found for URL: {url} (version: {version})"

    df = df.sort_values("chunk_index")
    title = df.iloc[0].get("title", "(no title)")
    full_content = "\n\n".join(df["content"].tolist())
    return f"# {title}\n\nSource: {url}\nVersion: {version}\n\n{full_content}"


def get_library_stats(library_name: str, version: str) -> dict | None:
    """Chunk/page counts and sample titles for a library version, or None if absent."""
    table = _get_table()
    if table is None:
        return None

    filter_str = _match(library_name, version)
    chunk_count = table.count_rows(filter=filter_str)
    if chunk_count == 0:
        return None

    df = table.search().where(filter_str).select(["title", "url"]).to_pandas()
    titles = [t for t in df["title"].unique().tolist() if t and str(t).strip()][:5]
    return {
        "library_name": library_name,
        "version": version,
        "chunk_count": chunk_count,
        "unique_urls": df["url"].nunique(),
        "titles": titles,
    }


def count_chunks() -> int:
    table = _get_table()
    return 0 if table is None else table.count_rows()


def delete_library(library_name: str, version: str) -> int:
    """Delete all chunks of a library version; returns the number deleted."""
    table = _get_table()
    if table is None:
        return 0

    filter_str = _match(library_name, version)
    count = table.count_rows(filter=filter_str)
    table.delete(filter_str)
    return count


def delete_urls(urls: list[str], library_name: str, version: str) -> int:
    """Delete all chunks of the given pages; returns the number deleted."""
    table = _get_table()
    if table is None or not urls:
        return 0

    url_conditions = " OR ".join(f"url = '{_escape_sql_string(u)}'" for u in urls)
    filter_str = f"{_match(library_name, version)} AND ({url_conditions})"
    count = table.count_rows(filter=filter_str)
    table.delete(filter_str)
    return count


def library_version_exists(library_name: str, version: str) -> bool:
    table = _get_table()
    return (
        table is not None and table.count_rows(filter=_match(library_name, version)) > 0
    )
