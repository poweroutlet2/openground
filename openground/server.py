import asyncio
import sys
from threading import Lock

from fastmcp import FastMCP

from openground.config import get_settings
from openground.console import UserError
from openground.mcp_cli import DEFAULT_HOST, DEFAULT_PORT
from openground.query import (
    FULL_CONTENT_TOOL,
    get_full_content,
    list_libraries_with_versions,
    search,
)
from openground.stats import increment_tool_call

mcp = FastMCP(
    "openground Documentation Search",
    instructions="""openground gives you access to official documentation for various libraries and frameworks. 
    
    CRITICAL RULES:
    1. Whenever a user asks about specific libraries or frameworks, you MUST first check if official documentation is available using this server.
    2. Do NOT rely on your internal training data for syntax or API details if you can verify them here.
    3. Always start by listing or searching available libraries to confirm coverage.
    4. If the library exists, use `search_documents_tool` to find the answer.""",
)


_search_lock = Lock()


def _search_documents(query: str, library_name: str, version: str) -> str:
    # Search can update the cached embedding settings to match the database.
    with _search_lock:
        return search(
            query=query,
            version=version,
            library_name=library_name,
            show_progress=False,
        )


@mcp.tool
async def search_documents_tool(
    query: str,
    library_name: str,
    version: str,
) -> str:
    """
    Search the official documentation knowledge base to answer user questions.

    Always used this tool when a question might be answered or confirmed from
    the documentation.

    First call list_libraries_tool to see what libraries and versions are available,
    then filter by library_name and version.
    """
    increment_tool_call("search_documents_tool")
    try:
        return await asyncio.to_thread(_search_documents, query, library_name, version)
    except UserError as e:
        return str(e)


@mcp.tool
def list_libraries_tool() -> dict[str, list[str]]:
    """
    Retrieve a dictionary of available documentation libraries/frameworks with their versions.

    Returns a dictionary mapping library names to lists of available versions.
    Use this tool to see what documentation is available before performing a search.
    If the desired library is not in the list, you may prompt the user to add it.
    """
    increment_tool_call("list_libraries_tool")
    return list_libraries_with_versions()


@mcp.tool(name=FULL_CONTENT_TOOL)
def get_full_content_tool(url: str, version: str) -> str:
    """
    Retrieve the full content of a document by its URL and version.

    Use this tool when you need to see the complete content of a page
    that was returned in search results. The URL and version are provided
    in the search result's tool hint.
    """
    increment_tool_call(FULL_CONTENT_TOOL)
    return get_full_content(url=url, version=version)


def run_server(
    transport: str = "stdio", host: str = DEFAULT_HOST, port: int = DEFAULT_PORT
):
    """Entry point for the MCP server."""
    try:
        get_settings()
    except UserError as e:
        sys.exit(f"[error] {e}")

    if transport == "http":
        mcp.run(transport="http", host=host, port=port, path="/mcp")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    from openground.mcp_cli import main

    main()
