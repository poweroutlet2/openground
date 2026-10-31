import functools
from typing import Callable, Optional

import typer

from openground.console import UserError, error, success, warning
from openground.install import Client

app = typer.Typer(
    help="Index documentation into a local vector database and search it from AI agents.",
    no_args_is_help=True,
    add_completion=False,
)


def _handle_errors(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except UserError as e:
            error(str(e))
            raise typer.Exit(1)

    return wrapper


def _show_version(value: bool) -> None:
    if value:
        from importlib.metadata import PackageNotFoundError, version

        try:
            typer.echo(version("openground"))
        except PackageNotFoundError:
            typer.echo("unknown")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_show_version, is_eager=True, help="Show version."
    ),
):
    pass


def _report(result) -> None:
    label = f"{result.library} ({result.version})"
    if result.error:
        error(f"{label}: {result.error}")
    elif result.summary is None:
        success(f"Added {label}: {result.pages} pages.")
    else:
        s = result.summary
        changes = (
            f"{s['added']} added, {s['modified']} modified, {s['deleted']} deleted"
        )
        if s["added"] + s["modified"] + s["deleted"] == 0:
            success(f"{label} is up to date.")
        else:
            success(f"Updated {label}: {changes}, {s['unchanged']} unchanged.")


@app.command()
@_handle_errors
def add(
    name: str = typer.Argument(..., help="Library name."),
    source: Optional[str] = typer.Argument(
        None,
        help="Git repo URL, sitemap URL, or local directory. Omit to reuse the remembered source.",
    ),
    docs_paths: list[str] = typer.Option(
        [], "--docs-path", "-d", help="Docs folder in a git repo (repeatable)."
    ),
    version: Optional[str] = typer.Option(
        None, "--version", "-v", help="Git tag or branch (git sources only)."
    ),
    filter_keywords: list[str] = typer.Option(
        [],
        "--filter",
        "-f",
        help="Only index sitemap URLs containing this (repeatable).",
    ),
):
    """Add a library. If this name and version are already stored, update it instead."""
    from openground.service import add_library

    _report(add_library(name, source, version, docs_paths, filter_keywords))


@app.command()
@_handle_errors
def update(
    name: Optional[str] = typer.Argument(
        None,
        help="Library to update. Omit to update every library with a remembered source.",
    ),
):
    """Refresh libraries from their remembered sources."""
    from openground.service import update_libraries

    results = update_libraries(name)
    if not results:
        warning("No libraries with a remembered source.")
    for result in results:
        _report(result)
    if any(r.error for r in results):
        raise typer.Exit(1)


@app.command()
@_handle_errors
def ls():
    """List stored libraries and versions."""
    from rich.console import Console
    from rich.table import Table

    from openground.service import list_libraries

    libraries = list_libraries()
    if not libraries:
        typer.echo("No libraries found. Add one with: openground add NAME SOURCE")
        return

    table = Table()
    table.add_column("Library", style="cyan", no_wrap=True)
    table.add_column("Versions", style="green")
    table.add_column("Source remembered")
    for name, versions, remembered in libraries:
        table.add_row(name, ", ".join(versions), "yes" if remembered else "no")
    Console().print(table)


@app.command()
@_handle_errors
def rm(
    name: str = typer.Argument(..., help="Library name."),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        "-v",
        help="Version to delete (optional if only one is stored).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    """Delete a library version and forget its source."""
    from openground.query import get_library_stats
    from openground.service import remove_library, resolve_version

    version = resolve_version(name, version)
    stats = get_library_stats(name, version) or {}
    if not yes:
        typer.confirm(
            f"Delete {name} ({version}): {stats.get('unique_urls', 0)} pages, "
            f"{stats.get('chunk_count', 0)} chunks?",
            abort=True,
        )
    remove_library(name, version)
    success(f"Removed {name} ({version}).")


@app.command()
@_handle_errors
def search(
    query: str = typer.Argument(..., help="Search query."),
    library: Optional[str] = typer.Option(
        None, "--library", "-l", help="Limit to a library."
    ),
    version: Optional[str] = typer.Option(
        None, "--version", "-v", help="Limit to a version."
    ),
    top_k: Optional[int] = typer.Option(
        None, "--top-k", "-k", help="Number of results."
    ),
):
    """Hybrid (semantic + keyword) search over stored docs."""
    from openground.query import search as run_search

    typer.echo(run_search(query, version=version, library_name=library, top_k=top_k))


@app.command()
@_handle_errors
def serve():
    """Run the MCP server on stdio (same as `openground-mcp`)."""
    from openground.config import get_settings
    from openground.server import run_server

    get_settings()
    run_server()


@app.command("install-mcp")
@_handle_errors
def install_mcp(
    client: Optional[Client] = typer.Argument(
        None, help="Client to configure. Omit to print the MCP JSON."
    ),
    wsl: bool = typer.Option(False, "--wsl", help="Launch the server through wsl.exe."),
):
    """Register the MCP server with an agent client."""
    from openground.install import install_to, mcp_config_json

    if client is None:
        typer.echo(mcp_config_json(wsl))
        typer.echo(
            "\nPaste this into your client's MCP config, or run "
            "`openground install-mcp claude-code|cursor|opencode`."
        )
        return
    install_to(client, wsl)


@app.command()
@_handle_errors
def config():
    """Show settings and data locations."""
    from openground.config import (
        get_config_path,
        get_data_home,
        get_settings,
        get_sources_path,
    )

    path = get_config_path()
    typer.echo(
        f"Config file: {path}"
        + ("" if path.exists() else " (not created; using defaults)")
    )
    typer.echo("Edit it to change settings; delete it to reset.\n")
    settings = get_settings()
    typer.echo(settings.model_dump_json(indent=2))
    typer.echo(f"\nDatabase:    {settings.db_path}")
    typer.echo(f"Raw files:   {settings.raw_data_dir}")
    typer.echo(f"Stats:       {get_data_home() / 'stats.json'}")
    typer.echo(f"Sources:     {get_sources_path()}")


@app.command()
@_handle_errors
def stats(
    reset: bool = typer.Option(False, "--reset", help="Zero the tool call counters."),
):
    """Show MCP tool call counts."""
    from openground.query import count_chunks, list_libraries_with_versions
    from openground.stats import load_tool_calls, reset_stats

    if reset:
        reset_stats()
        success("Tool call counts reset.")
        return

    calls = load_tool_calls()
    typer.echo(f"Libraries: {len(list_libraries_with_versions())}")
    typer.echo(f"Chunks:    {count_chunks()}")
    typer.echo("Tool calls:")
    for tool, count in sorted(calls.items()):
        typer.echo(f"  {tool}: {count}")


@app.command()
@_handle_errors
def reset(yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation.")):
    """Delete ALL local data (embeddings, raw files, stats). Remembered sources are kept."""
    from openground.config import get_data_home
    from openground.service import reset_data

    if not yes:
        typer.confirm(f"Delete everything in {get_data_home()}?", abort=True)
    reset_data()
    success("All local data deleted.")


if __name__ == "__main__":
    app()
