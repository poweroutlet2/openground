import os
import sys
import threading
import time

# Silence stdout pollution from dependencies
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["FAST_EMBED_IGNORE_TRANSFORMERS_LOGS"] = "1"

from fastmcp import FastMCP

from openground.query import (
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


def _pre_load_resources():
    """Warm up caches and pre-load embedding models in the background."""
    start_time = time.time()
    sys.stderr.write("[info] Background initialization started...\n")
    try:
        list_libraries_with_versions()

        from openground.embeddings import generate_embeddings

        generate_embeddings(["warmup"], show_progress=False)

        duration = time.time() - start_time
        sys.stderr.write(
            f"[info] Background initialization complete (took {duration:.2f}s). Server is fully ready.\n"
        )
    except Exception as e:
        # Background tasks should never crash the server
        sys.stderr.write(f"[error] Background initialization failed: {e}\n")


@mcp.tool
def search_documents_tool(
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
    available_libraries = list_libraries_with_versions()

    if library_name not in available_libraries:
        available_lib_names = ", ".join(sorted(available_libraries.keys()))
        if available_lib_names:
            return f"Library '{library_name}' not found. Available libraries: {available_lib_names}"
        else:
            return f"Library '{library_name}' not found. No libraries are currently available in the database."

    available_versions = available_libraries[library_name]
    if version not in available_versions:
        versions_str = ", ".join(available_versions)
        return f"Version '{version}' not found for library '{library_name}'. Available versions: {versions_str}"

    # Library and version exist, proceed with search
    return search(
        query=query,
        version=version,
        library_name=library_name,
        show_progress=False,
    )


@mcp.tool
def list_libraries_tool() -> dict[str, list[str]]:
    """
    Retrieve a dictionary of available documentation libraries/frameworks with their versions.

    Returns a dictionary mapping library names to lists of available versions.
    Use this tool to see what documentation is available before performing a search.
    If the desired library is not in the list, you may prompt the user to add it.

    Args:
        search_term: Optional search term to filter library names (case-insensitive).
                     If provided, only libraries whose names contain the search term will be returned.
    """
    increment_tool_call("list_libraries_tool")
    return list_libraries_with_versions()


@mcp.tool
def get_full_content_tool(url: str, version: str) -> str:
    """
    Retrieve the full content of a document by its URL and version.

    Use this tool when you need to see the complete content of a page
    that was returned in search results. The URL and version are provided
    in the search result's tool hint.
    """
    increment_tool_call("get_full_content_tool")
    return get_full_content(url=url, version=version)


def run_server():
    """Entry point for the MCP server."""
    threading.Thread(target=_pre_load_resources, daemon=True).start()

    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
