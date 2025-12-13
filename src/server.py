from fastmcp import FastMCP
from query import get_full_content, list_libraries, search, search_libraries

from src.config import DEFAULT_DB_PATH, DEFAULT_TABLE_NAME

mcp = FastMCP(
    "OpenGround Documentation Search",
    instructions="OpenGround gives you access to up-to-date official documentation for various libraries and frameworks",
)


@mcp.tool
def search_documents_tool(
    query: str,
    library_name: str,
) -> str:
    """
    Search the official documentation knowledge base to answer user questions.

    Use this to answer user questions about our docs/how-tos/features.
    Always call this when a question might be answered from the docs.
    First call list_libraries to see what libraries are available,
    then filter by library_name.
    """
    return search(
        query=query,
        db_path=DEFAULT_DB_PATH,
        table_name=DEFAULT_TABLE_NAME,
        library_name=library_name,
        top_k=5,
    )


@mcp.tool
def list_libraries_tool() -> list[str]:
    """
    Retrieve a list of available documentation libraries/frameworks.

    Use this tool if you need to see what documentation is available
    before performing a search, or to verify if a specific library exists.
    If the desired library is not in the list, you may prompt the user
    to add it.
    """
    return list_libraries(db_path=DEFAULT_DB_PATH, table_name=DEFAULT_TABLE_NAME)


@mcp.tool
def search_available_libraries_tool(search_term: str) -> list[str]:
    """
    Search for available documentation libraries by name.

    Use this tool to find libraries matching a search term.
    Returns libraries whose names contain the search term (case-insensitive).
    """
    return search_libraries(
        search_term=search_term,
        db_path=DEFAULT_DB_PATH,
        table_name=DEFAULT_TABLE_NAME,
    )


@mcp.tool
def get_full_content_tool(url: str) -> str:
    """
    Retrieve the full content of a document by its URL.

    Use this tool when you need to see the complete content of a page
    that was returned in search results. The URL is provided in the
    search result's tool hint.
    """
    return get_full_content(
        url=url,
        db_path=DEFAULT_DB_PATH,
        table_name=DEFAULT_TABLE_NAME,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
