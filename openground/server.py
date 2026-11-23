import asyncio
import sys

from fastmcp import FastMCP
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from openground.config import get_settings, read_settings
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


class MCPRequestValidation:
    """Validate HTTP authorities and browser origins before opening MCP sessions."""

    def __init__(self, app: ASGIApp, host: str, port: int):
        self.app = app
        host = host.lower()
        hosts = {"localhost", "127.0.0.1", "[::1]"}
        if host not in {"0.0.0.0", "::"}:
            hosts.add(f"[{host}]" if ":" in host else host)
        self.allowed_hosts = {f"{name}:{port}" for name in hosts}
        if port == 80:
            self.allowed_hosts.update(hosts)
        self.allowed_origins = {f"http://{name}" for name in self.allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            origins = headers.getlist("origin")
            if origins and (
                len(origins) != 1 or origins[0] not in self.allowed_origins
            ):
                await PlainTextResponse("Invalid Origin header", status_code=403)(
                    scope, receive, send
                )
                return
            hosts = headers.getlist("host")
            if len(hosts) != 1 or hosts[0].lower() not in self.allowed_hosts:
                await PlainTextResponse("Invalid Host header", status_code=421)(
                    scope, receive, send
                )
                return
        await self.app(scope, receive, send)


def _search_documents(query: str, library_name: str, version: str) -> str:
    return search(
        query,
        version=version,
        library_name=library_name,
        show_progress=False,
        settings=read_settings(),
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
        mcp.run(
            transport="http",
            host=host,
            port=port,
            path="/mcp",
            middleware=[Middleware(MCPRequestValidation, host=host, port=port)],
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    from openground.mcp_cli import main

    main()
