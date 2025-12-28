from pathlib import Path

from fastmcp import FastMCP

from openground.config import get_effective_config
from openground.query import get_full_content, list_libraries, search, search_libraries

mcp = FastMCP(
    "openground Documentation Search",
    instructions="""openground gives you access to official documentation for various libraries and frameworks. 
    
    CRITICAL RULES:
    1. Whenever a user asks about specific libraries or frameworks, you MUST first check if official documentation is available using this server.
    2. Do NOT rely on your internal training data for syntax or API details if you can verify them here.
    3. Always start by listing or searching available libraries to confirm coverage.
    4. If the library exists, use `search_documents_tool` to find the answer.""",
)

_config = None


def _get_config():
    """Get effective config, loading it once and caching."""
    global _config
    if _config is None:
        _config = get_effective_config()
    return _config


@mcp.tool
def search_documents_tool(
    query: str,
    library_name: str,
) -> str:
    """
    Search the official documentation knowledge base to answer user questions.

    Always used this tool when a question might be answered or confirmed from
    the documentation.

    First call list_libraries to see what libraries are available, then filter
    by library_name.
    """
    config = _get_config()
    return search(
        query=query,
        db_path=Path(config["db_path"]).expanduser(),
        table_name=config["table_name"],
        library_name=library_name,
        top_k=config["query"]["top_k"],
    )


@mcp.tool
def list_libraries_tool() -> list[str]:
    """
    Retrieve a list of available documentation libraries/frameworks.

    Use this tool to see what documentation is available before performing a
    search. If the desired library is not in the list, you may prompt the user
    to add it.
    """
    config = _get_config()
    return list_libraries(
        db_path=Path(config["db_path"]).expanduser(), table_name=config["table_name"]
    )


@mcp.tool
def search_available_libraries_tool(search_term: str) -> list[str]:
    """
    Search for available documentation libraries by name.

    Use this tool to find libraries matching a search term.
    Returns libraries whose names contain the search term (case-insensitive).
    """
    config = _get_config()
    return search_libraries(
        search_term=search_term,
        db_path=Path(config["db_path"]).expanduser(),
        table_name=config["table_name"],
    )


@mcp.tool
def get_full_content_tool(url: str) -> str:
    """
    Retrieve the full content of a document by its URL.

    Use this tool when you need to see the complete content of a page
    that was returned in search results. The URL is provided in the
    search result's tool hint.
    """
    config = _get_config()
    return get_full_content(
        url=url,
        db_path=Path(config["db_path"]).expanduser(),
        table_name=config["table_name"],
    )


def run_server():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
