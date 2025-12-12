from pathlib import Path
from typing import Optional
import lancedb
from fastmcp import FastMCP
from query import search

DB_PATH = "lancedb_data"
TABLE_NAME = "documents"

mcp = FastMCP("Documentation Search")


@mcp.tool
def search_documents(
    query: str,
    collection_title: Optional[str] = None,
) -> str:
    """
    Search the documentation knowledge base to answer user questions.

    Use this to answer user questions about our docs/how-tos/features.
    Always call this when a question might be answered from the docs.
    First call list_collections to see what collections are available,
    then filter by collection_title.
    """
    return search(
        query=query,
        db_path=Path(DB_PATH),
        table_name=TABLE_NAME,
        collection_title=collection_title,
        top_k=5,
    )


@mcp.tool
def list_collections() -> list[str]:
    """
    Retrieve a list of available documentation topics/collections.

    Use this tool if you need to see what documentation is available
    before performing a search, or to verify if a specific topic exists.
    """
    db = lancedb.connect(DB_PATH)
    table = db.open_table(TABLE_NAME)
    df = table.to_pandas()
    collections = df["collection_title"].dropna().unique().tolist()
    return sorted(collections)


if __name__ == "__main__":
    mcp.run(transport="stdio")
