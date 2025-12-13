from pathlib import Path

from fastmcp import FastMCP
from query import get_full_content as get_full_content_from_db, list_libraries, search

DB_PATH = "lancedb"
TABLE_NAME = "documents"

mcp = FastMCP("Documentation Search")


@mcp.tool
def search_documents(
    query: str,
    collection_title: str,
) -> str:
    """
    Search the official documentation knowledge base to answer user questions.

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
    If the desired collection is not in the list, you may prompt the user
    to add it.
    """
    return list_libraries(db_path=Path(DB_PATH), table_name=TABLE_NAME)


@mcp.tool
def get_full_content(url: str) -> str:
    """
    Retrieve the full content of a document by its URL.

    Use this tool when you need to see the complete content of a page
    that was returned in search results. The URL is provided in the
    search result's tool hint.
    """
    return get_full_content_from_db(
        url=url,
        db_path=Path(DB_PATH),
        table_name=TABLE_NAME,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
