import asyncio
import json
import platform
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from openground.config import (
    DEFAULT_LIBRARY_NAME,
    SITEMAP_URL,
    get_library_raw_data_dir,
    get_config_path,
    load_config,
    save_config,
    get_effective_config,
    get_default_config,
    clear_config_cache,
    DEFAULT_LIBRARY_VERSION,
)
from openground.console import success, error, hint, warning
from openground.extract.source import get_library_config, get_source_file_path
from openground.query import library_version_exists


app = typer.Typer(
    help="Openground is a CLI for storing and querying documentation in a local vector database.",
    no_args_is_help=True,
)

# Config Sub App
config_app = typer.Typer(help="Manage openground configuration.")
app.add_typer(config_app, name="config")

# Nuke Sub App
nuke_app = typer.Typer(
    help="Delete all data from raw_data and/or LanceDB.",
    no_args_is_help=True,
)
app.add_typer(nuke_app, name="nuke")

# Stats Sub App
stats_app = typer.Typer(
    help="View and manage openground statistics.",
    no_args_is_help=True,
)
app.add_typer(stats_app, name="stats")


@app.callback(invoke_without_command=True)
def ensure_config_exists(ctx: typer.Context):
    """Ensure config file exists before running any command."""
    # Avoid side effects (like writing config files) when Typer is doing
    # resilient parsing (e.g. for --help, completion, etc.).
    if getattr(ctx, "resilient_parsing", False):
        return

    config_path = get_config_path()
    file_existed = config_path.exists()

    # Explicitly create config file with defaults if it doesn't exist
    if not config_path.exists():
        default_config = get_default_config()
        save_config(default_config)

    # Load the effective config (now that we know it exists)
    get_effective_config()

    # Notify user if we just created it
    if not file_existed and config_path.exists():
        success(f"Config file created at {config_path}\n")


@app.command("version")
def version_cmd():
    """Display the openground version."""
    try:
        from importlib.metadata import version

        v = version("openground")
        print(v)
    except Exception:
        # Fallback if package metadata is not available
        print("unknown")


@app.command("add")
def add(
    library: str = typer.Argument(
        ..., help="Name of the library (or source key if no source is provided)."
    ),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Root sitemap URL or Git repo URL to crawl."
    ),
    version: str | None = typer.Option(
        None,
        "--version",
        "-v",
        help="Version of the library to extract. Only works for git repos. Corresponds to the tag of the version in the git repo. Defaults to latest. Sitemap sources will always use latest.",
    ),
    docs_paths: list[str] = typer.Option(
        [],
        "--docs-path",
        "-d",
        help="Path to documentation within a git repo. Specify multiple times for multiple paths (e.g., -d docs/ -d wiki/). Defaults to '/' if not specified.",
    ),
    filter_keywords: list[str] = typer.Option(
        [],
        "--filter-keyword",
        "-f",
        help="String filter for sitemap URLs. Only used for sitemap sources. Can be specified multiple times (e.g., -f docs -f /blog)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt between extract and ingest.",
    ),
    sources_file: Optional[str] = typer.Option(
        None,
        "--sources-file",
        help="Path to a custom sources.json file. If not provided, checks config for 'sources.file_path', then uses default.",
    ),
    trim_query_params: bool = typer.Option(
        False,
        "--trim-query-params",
        help="Trim query parameters from sitemap URLs to avoid duplicates.",
    ),
):
    """
    Extract documentation from a source (source file, sitemap, or git) and ingest it.

    This command detects the source type and performs the extraction
    and ingestion in one step.

    For git sources, the following file extensions are parsed: .md, .rst, .txt, .mdx, .ipynb
    """
    from rich.console import Console

    console = Console()
    config = get_effective_config()

    # Determine which sources file to use (CLI option > config > default)
    sources_file_path: Optional[Path] = None
    if sources_file:
        sources_file_path = Path(sources_file).expanduser()
    elif "sources" in config and "file_path" in config["sources"]:
        sources_file_path = Path(config["sources"]["file_path"]).expanduser()

    # Resolve configuration from source file if possible (only if source is not provided)
    source_config, actual_sources_path = None, None
    if not source:
        source_config, actual_sources_path = get_library_config(
            library, custom_path=sources_file_path
        )

    # Print which sources file is being used if a config was found
    if source_config and actual_sources_path:
        hint(f"Using sources file: {actual_sources_path}")
    source_type = None
    final_source = source
    final_docs_paths = docs_paths
    final_filter_keywords = filter_keywords

    if source_config:
        source_type = source_config.get("type")
        if not final_source:
            if source_type == "sitemap":
                final_source = source_config.get("sitemap_url")
            elif source_type == "git_repo":
                final_source = source_config.get("repo_url")

        if not final_docs_paths and source_type == "git_repo":
            # Map 'docs_paths' from current json to final_docs_paths
            final_docs_paths = source_config.get("docs_paths", [])

        if not final_filter_keywords and source_type == "sitemap":
            final_filter_keywords = source_config.get("filter_keywords", [])

    if version is None:
        version = DEFAULT_LIBRARY_VERSION

    # Detect if source is provided manually or type is unknown
    if not final_source:
        error(
            f"No source provided for library '{library}'. "
            f"Please provide a --source URL or use a library from the source file."
        )
        raise typer.Exit(1)

    if not source_type:
        # Detect type from URL
        if any(domain in final_source for domain in ["github.com", "gitlab.com"]):
            from openground.extract.git import parse_git_web_url

            repo_url, ref, doc_path = parse_git_web_url(final_source)
            if repo_url != final_source:
                final_source = repo_url
                if ref and not version:
                    version = ref
                if doc_path and not final_docs_paths:
                    final_docs_paths = [doc_path]

            source_type = "git_repo"
            if not final_docs_paths:
                final_docs_paths = ["/"]
        elif final_source.endswith(".xml") or "sitemap" in final_source.lower():
            source_type = "sitemap"
        else:
            # Try sitemap by default with warning
            source_type = "sitemap"
            warning(
                f"Could not reliably detect source type for {final_source}. Defaulting to sitemap."
            )

    if version is not None and version != DEFAULT_LIBRARY_VERSION:
        if source_type != "git_repo":
            error(
                f"--version can only be used for git repo sources. Detected source type '{source_type}' is not a git repo."
            )
            raise typer.Exit(1)

    # Extract
    # Determine version for directory path (always a string, defaults to "latest")
    output_dir = get_library_raw_data_dir(library, version=version)

    # Check if library version exists in LanceDB BEFORE extraction
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]
    library_exists = library_version_exists(library, version, db_path, table_name)

    # Handle case where library doesn't exist in LanceDB but raw files do
    if not library_exists and output_dir.exists() and list(output_dir.glob("*.json")):
        warning(
            f"Found stale raw data files for '{library}' version '{version}' "
            "that are not in LanceDB. Cleaning up..."
        )
        import shutil

        try:
            shutil.rmtree(output_dir)
        except (FileNotFoundError, OSError) as e:
            warning(f"Could not remove stale files: {e}")
        library_exists = False

    if library_exists:
        print(f"Library '{library}' version '{version}' already exists.")
        print("Performing extraction and incremental update...")

    async def _run_extract():
        if source_type == "sitemap":
            with console.status("[bold green]"):
                from openground.extract.sitemap import extract_pages as extract_main

            await extract_main(
                sitemap_url=final_source,
                concurrency_limit=config["extraction"]["concurrency_limit"],
                library_name=library,
                output_dir=output_dir,
                filter_keywords=final_filter_keywords,
                version=version,
                trim_query_params=trim_query_params,
            )
        elif source_type == "git_repo":
            with console.status("[bold green]"):
                from openground.extract.git import extract_repo

            await extract_repo(
                repo_url=final_source,
                docs_paths=final_docs_paths if final_docs_paths else ["/"],
                output_dir=output_dir,
                library_name=library,
                version=version,
            )

    with console.status("[bold green]"):
        from openground.ingest import ingest_to_lancedb, load_parsed_pages

    asyncio.run(_run_extract())

    # Embed
    if not output_dir.exists():
        raise typer.BadParameter(
            f"Extraction completed but data directory not found at {output_dir}."
        )

    page_count = len(list(output_dir.glob("*.json")))
    success(f"\nExtraction complete: {page_count} pages extracted to {output_dir}")

    if library_exists:
        from openground.update import perform_update

        pages = load_parsed_pages(output_dir)

        try:
            summary = perform_update(
                extracted_pages=pages,
                library_name=library,
                version=version,
                db_path=db_path,
                table_name=table_name,
                raw_data_dir=output_dir,
            )

            print("\nUpdate Summary:")
            print(f"  Added: {summary['added']} pages")
            print(f"  Modified: {summary['modified']} pages")
            print(f"  Deleted: {summary['deleted']} pages")
            print(f"  Unchanged: {summary['unchanged']} pages")

            if summary["added"] + summary["modified"] + summary["deleted"] == 0:
                success("No changes detected. Nothing to update.")
                return

            success(f"Update complete: {library} ({version}) updated.")
            return
        except ValueError as e:
            if "produced no pages" in str(e):
                error(f"{e}")
                raise typer.Exit(1)
            raise

    if not yes:
        print("\nPress Enter to continue with embedding, or Ctrl+C to exit...")
        try:
            input()
        except KeyboardInterrupt:
            error("\nCancelled by user.")
            raise typer.Abort()

    pages = load_parsed_pages(output_dir)
    ingest_to_lancedb(pages=pages)
    success(f"Embedding complete: Library {library} ({version}) added to LanceDB.")

    # Auto-add to local sources.json if configured and source was provided manually
    if source and config.get("sources", {}).get("auto_add_local", True):
        from openground.extract.source import save_source_to_sources, LibrarySource

        new_source_config: LibrarySource = {
            "type": source_type,  # type: ignore
        }
        if source_type == "sitemap":
            new_source_config["sitemap_url"] = final_source
            if final_filter_keywords:
                new_source_config["filter_keywords"] = final_filter_keywords
        elif source_type == "git_repo":
            new_source_config["repo_url"] = final_source
            if final_docs_paths:
                new_source_config["docs_paths"] = final_docs_paths

        save_source_to_sources(library, new_source_config)
        success(f"Added source for '{library}' to ~/.openground/sources.json")
        hint(
            "Tip: Disable automatic addition to user sources by running:\n"
            "  openground config set sources.auto_add_local false"
        )


@app.command("update")
def update_library(
    library: str = typer.Argument(..., help="Name of the library to update."),
    version: str = typer.Option("latest", "--version", "-v", help="Version to update."),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Override source URL."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip prompts."),
):
    """
    Update an existing library with changes from the source.

    Efficiently updates only changed pages by comparing content hashes.
    This is an alias for the add command when a library already exists.
    """
    add(
        library=library,
        source=source,
        version=version,
        docs_paths=[],
        filter_keywords=[],
        yes=yes,
        sources_file=None,
        trim_query_params=False,
    )


@app.command()
def extract_sitemap(
    sitemap_url: str = typer.Option(
        SITEMAP_URL, "--sitemap-url", "-s", help="Root sitemap URL to crawl."
    ),
    library: str = typer.Option(
        DEFAULT_LIBRARY_NAME,
        "--library",
        "-l",
        help="Name of the library/framework for this documentation.",
    ),
    filter_keywords: list[str] = typer.Option(
        [],
        "--filter-keyword",
        "-f",
        help="Keyword filter applied to sitemap URLs. If none are provided, all URLs are extracted. Can be specified multiple times (e.g., -f docs -f /blog).",
    ),
    concurrency_limit: int | None = typer.Option(
        None,
        "--concurrency-limit",
        "-c",
        help="Maximum number of concurrent requests.",
        min=1,
    ),
    trim_query_params: bool = typer.Option(
        False,
        "--trim-query-params",
        help="Trim query parameters from sitemap URLs to avoid duplicates.",
    ),
):
    """Run the extraction pipeline to fetch and parse pages from a sitemap."""

    from openground.extract.sitemap import extract_pages

    config = get_effective_config()

    if concurrency_limit is None:
        concurrency_limit = config["extraction"]["concurrency_limit"]

    # Ensure concurrency_limit is an int for the type checker
    limit: int = concurrency_limit  # type: ignore

    version = "latest"
    output_dir = get_library_raw_data_dir(library, version=version)

    async def _run():
        await extract_pages(
            sitemap_url=sitemap_url,
            concurrency_limit=limit,
            library_name=library,
            output_dir=output_dir,
            filter_keywords=filter_keywords,
            version=version,
            trim_query_params=trim_query_params,
        )

    asyncio.run(_run())


@app.command("extract-git")
def extract_git(
    repo_url: str = typer.Option(..., "--repo-url", "-r", help="Git repository URL."),
    docs_paths: list[str] = typer.Option(
        ...,
        "--docs-path",
        "-d",
        help="Path to documentation within the repo. Specify multiple times for multiple paths (e.g., -d docs/ -d wiki/). Use '/' for the whole repo.",
    ),
    library: str = typer.Option(
        DEFAULT_LIBRARY_NAME,
        "--library",
        "-l",
        help="Name of the library/framework for this documentation.",
    ),
    version: str = typer.Option(
        "latest",
        "--version",
        "-v",
        help="Version of the library to extract. Corresponds to the tag of the version in the git repo. Defaults to latest.",
    ),
):
    """Extract documentation from a git repository using shallow clone and sparse checkout."""
    from openground.extract.git import extract_repo

    output_dir = get_library_raw_data_dir(library, version=version)

    async def _run():
        await extract_repo(
            repo_url=repo_url,
            docs_paths=docs_paths,
            output_dir=output_dir,
            library_name=library,
            version=version,
        )

    asyncio.run(_run())


@app.command("embed")
def embed(
    library: str = typer.Argument(
        ...,
        help="Library name to embed from raw_data/{library}.",
    ),
    version: str = typer.Option(
        "latest",
        "--version",
        "-v",
        help="Version of the library to embed.",
    ),
):
    """Chunk documents, generate embeddings, and embed into the local db."""
    from rich.console import Console

    console = Console()
    with console.status("[bold green]"):
        from openground.ingest import ingest_to_lancedb, load_parsed_pages

    data_dir = get_library_raw_data_dir(library, version=version)

    if not data_dir.exists():
        raise typer.BadParameter(
            f"Library '{library}'"
            + (f" version '{version}'" if version else "")
            + f" not found at {data_dir}. "
            f"Use 'list-raw-libraries' to see available libraries."
        )

    pages = load_parsed_pages(data_dir)
    ingest_to_lancedb(pages=pages)


@app.command("query")
def query_cmd(
    query: str = typer.Argument(..., help="Query string for hybrid search."),
    version: str = typer.Option(
        DEFAULT_LIBRARY_VERSION, "--version", "-v", help="Version to filter results by."
    ),
    library: Optional[str] = typer.Option(
        None,
        "--library",
        "-l",
        help="Optional library name filter.",
    ),
    top_k: int | None = typer.Option(
        None, "--top-k", "-k", help="Number of results to return."
    ),
):
    """Run a hybrid search (semantic + BM25) against the local db."""
    from openground.query import search

    # Get config
    config = get_effective_config()

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    # Use CLI flag if provided, otherwise use config value
    if top_k is None:
        top_k = config["query"]["top_k"]

    # Ensure top_k is an int for the type checker
    k: int = top_k  # type: ignore

    results_md = search(
        query=query,
        version=version,
        db_path=db_path,
        table_name=table_name,
        library_name=library,
        top_k=k,
    )
    print(results_md)


@app.command("list-libraries")
@app.command("ls")
def list_libraries_cmd():
    """List available libraries and their versions stored in the local db."""
    from rich.console import Console

    console = Console()
    with console.status("[bold green]"):
        from openground.query import list_libraries_with_versions

    # Get config
    config = get_effective_config()

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    libraries_with_versions = list_libraries_with_versions(
        db_path=db_path, table_name=table_name
    )
    if not libraries_with_versions:
        print("No libraries found.")
        return

    for lib_name, versions in libraries_with_versions.items():
        versions_str = ", ".join(versions)
        print(f"{lib_name}: {versions_str}")


@app.command("list-raw-libraries")
def list_raw_libraries_cmd():
    """List available libraries in the raw_data directory."""
    config = get_effective_config()
    raw_data_dir = Path(config["raw_data_dir"]).expanduser()
    if not raw_data_dir.exists():
        print("No libraries found in raw_data.")
        return

    libraries_with_versions: dict[str, list[str]] = {}
    for lib_dir in raw_data_dir.iterdir():
        if lib_dir.is_dir():
            lib_name = lib_dir.name
            versions = [d.name for d in lib_dir.iterdir() if d.is_dir()]
            if versions:
                libraries_with_versions[lib_name] = sorted(versions)

    if not libraries_with_versions:
        print("No libraries found in raw_data.")
        return

    print("Available libraries in raw_data:")
    for lib_name, versions in sorted(libraries_with_versions.items()):
        versions_str = ", ".join(versions)
        print(f"{lib_name}: {versions_str}")


@app.command("remove")
@app.command("rm")
def remove_library_cmd(
    library_name: str = typer.Argument(..., help="Name of the library to remove."),
    version: str = typer.Option(
        ..., "--version", "-v", help="Version of the library to remove."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Remove all documents for a library version from the local db."""
    from openground.query import get_library_stats, delete_library

    # Get config
    config = get_effective_config()

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    stats = get_library_stats(library_name, version, db_path, table_name)
    if not stats:
        print(f"Library '{library_name}' version '{version}' not found.")
        raise typer.Exit(1)

    # Show confirmation info
    print(f"\nLibrary: {stats['library_name']}")
    print(f"Version: {stats['version']}")
    print(f"  Chunks: {stats['chunk_count']}")
    print(f"  Pages:  {stats['unique_urls']}")
    if stats["titles"]:
        print(f"  Sample titles: {', '.join(stats['titles'][:3])}")
    else:
        print("  Sample titles: (no titles available)")

    if not yes:
        typer.confirm(
            "\nAre you sure you want to delete this library version?", abort=True
        )

    deleted = delete_library(library_name, version, db_path, table_name)
    success(
        f"\nDeleted {deleted} chunks for library '{library_name}' version '{version}'."
    )

    # Check if raw library directory exists and offer to delete
    if not yes:
        raw_library_dir = get_library_raw_data_dir(library_name, version=version)
        if raw_library_dir.exists():
            if typer.confirm(f"\nAlso delete raw files at {raw_library_dir}?"):
                import shutil

                shutil.rmtree(raw_library_dir)
                success(f"Deleted raw library files at {raw_library_dir}.")


def _install_to_claude_code() -> None:
    """Install openground to Claude Code using the claude CLI."""
    try:
        # First, remove any existing openground MCP config to ensure clean install
        print("Removing existing openground MCP config if it exists...")
        remove_cmd = [
            "claude",
            "mcp",
            "remove",
            "openground",
            "--scope",
            "user",
        ]
        subprocess.run(
            remove_cmd,
            capture_output=True,
            check=False,
        )

        # Build the command - uses the openground-mcp entry point
        cmd = [
            "claude",
            "mcp",
            "add",
            "--transport",
            "stdio",
            "--scope",
            "user",
            "openground",
            "--",
            "openground-mcp",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            success("Successfully installed openground to Claude Code!")
            if result.stdout:
                print(result.stdout)
        else:
            error("Failed to install to Claude Code.")
            if result.stderr:
                print(f"Error: {result.stderr}")
            if result.stdout:
                print(f"Output: {result.stdout}")
            sys.exit(1)

    except FileNotFoundError:
        error("Error: 'claude' CLI not found in PATH.")
        print("\nPlease install Claude Code CLI first:")
        print("  https://code.claude.com/docs/en/cli")
        print("\nAlternatively, you can manually install by running:")
        print("  openground install-mcp")
        print("  (without --claude-code flag)")
        sys.exit(1)
    except Exception as e:
        error(f"Error installing to Claude Code: {e}")
        print("\nYou can manually install by running:")
        print("  openground install-mcp")
        print("  (without --claude-code flag)")
        sys.exit(1)


def _get_cursor_config_path() -> Path:
    """Determine the Cursor MCP config file path based on OS."""
    system = platform.system()
    if system == "Windows":
        # Windows: %APPDATA%\Cursor\mcp.json
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "Cursor" / "mcp.json"
    elif system == "Darwin":  # macOS
        # macOS: ~/.cursor/mcp.json
        return Path.home() / ".cursor" / "mcp.json"
    else:  # Linux and others
        # Linux: ~/.config/cursor/mcp.json
        return Path.home() / ".cursor" / "mcp.json"


def _get_opencode_config_path() -> Path:
    """Determine the OpenCode config file path."""
    return Path.home() / ".config" / "opencode" / "opencode.json"


def _find_openground_mcp_command() -> str:
    """Find the openground-mcp command, returning full path if found, otherwise the command name."""
    import shutil

    command_path = shutil.which("openground-mcp")
    if command_path:
        return str(Path(command_path).resolve())
    return "openground-mcp"


def _install_to_cursor() -> None:
    """Safely install openground to Cursor's MCP configuration."""
    config_path = _get_cursor_config_path()

    # Create parent directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config or start with empty structure
    existing_config = {"mcpServers": {}}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():  # Only parse if file has content
                    existing_config = json.loads(content)
                    # Ensure mcpServers key exists
                    if "mcpServers" not in existing_config:
                        existing_config["mcpServers"] = {}
        except json.JSONDecodeError as e:
            error(f"Error: {config_path} contains invalid JSON.")
            print(f"   Parse error: {e}")
            print("\nPlease fix the file manually or delete it to start fresh.")
            sys.exit(1)
        except Exception as e:
            error(f"Error reading {config_path}: {e}")
            sys.exit(1)

    # Check if openground already exists
    if "openground" in existing_config.get("mcpServers", {}):
        warning("Warning: 'openground' is already configured in Cursor.")
        print("Current config will be updated.")

    # Create backup before modifying
    if config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.parent / f"{config_path.name}.backup.{timestamp}"
        try:
            import shutil

            shutil.copy2(config_path, backup_path)
            print(f"Created backup: {backup_path}")
        except Exception as e:
            warning(f"Warning: Could not create backup: {e}")
            print("Proceeding without backup...")

    # Build new config - uses the openground-mcp entry point
    mcp_command = _find_openground_mcp_command()
    new_server_config = {
        "command": mcp_command,
    }

    # Merge into existing config
    existing_config["mcpServers"]["openground"] = new_server_config

    # Write atomically: write to temp file, validate, then rename
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            # Write JSON with proper formatting
            json.dump(existing_config, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)

        # Validate the temp file is valid JSON
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()  # Clean up temp file
            error(f"Error: Generated configuration is invalid JSON: {e}")
            sys.exit(1)

        # Atomic rename
        if tmp_path:
            tmp_path.replace(config_path)
        success("Successfully installed openground to Cursor!")
        print(f"   Configuration written to: {config_path}")
        hint("\nRestart Cursor to apply changes.")

    except PermissionError:
        error(f"Error: Permission denied writing to {config_path}")
        print("   Please check file permissions or run with appropriate privileges.")
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        sys.exit(1)
    except Exception as e:
        error(f"Error writing configuration: {e}")
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        sys.exit(1)


def _install_to_opencode() -> None:
    """Safely install openground to OpenCode's MCP configuration."""
    config_path = _get_opencode_config_path()

    # Create parent directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config or start with empty structure
    existing_config = {"mcp": {}}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():  # Only parse if file has content
                    existing_config = json.loads(content)
                    # Ensure mcp key exists
                    if "mcp" not in existing_config:
                        existing_config["mcp"] = {}
        except json.JSONDecodeError as e:
            error(f"Error: {config_path} contains invalid JSON.")
            print(f"   Parse error: {e}")
            print("\nPlease fix the file manually or delete it to start fresh.")
            sys.exit(1)
        except Exception as e:
            error(f"Error reading {config_path}: {e}")
            sys.exit(1)

    # Check if openground already exists
    if "openground" in existing_config.get("mcp", {}):
        warning("Warning: 'openground' is already configured in OpenCode.")
        print("Current config will be updated.")

    # Create backup before modifying
    if config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.parent / f"{config_path.name}.backup.{timestamp}"
        try:
            import shutil

            shutil.copy2(config_path, backup_path)
            print(f"Created backup: {backup_path}")
        except Exception as e:
            warning(f"Warning: Could not create backup: {e}")
            print("Proceeding without backup...")

    # Build new config - uses the openground-mcp entry point
    mcp_command = _find_openground_mcp_command()
    new_server_config = {
        "type": "local",
        "command": [mcp_command],
        "enabled": True,
    }

    # Merge into existing config
    existing_config["mcp"]["openground"] = new_server_config

    # Write atomically: write to temp file, validate, then rename
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            # Write JSON with proper formatting
            json.dump(existing_config, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)

        # Validate the temp file is valid JSON
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()  # Clean up temp file
            error(f"Error: Generated configuration is invalid JSON: {e}")
            sys.exit(1)

        # Atomic rename
        if tmp_path:
            tmp_path.replace(config_path)
        success("Successfully installed openground to OpenCode!")
        print(f"   Configuration written to: {config_path}")
        hint("\nRestart OpenCode to apply changes.")

    except PermissionError:
        error(f"Error: Permission denied writing to {config_path}")
        print("   Please check file permissions or run with appropriate privileges.")
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        sys.exit(1)
    except Exception as e:
        error(f"Error writing configuration: {e}")
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        sys.exit(1)


@app.command("install-mcp")
def install_cmd(
    claude_code: bool = typer.Option(
        False,
        "--claude-code",
        help="Automatically install to Claude Code using the claude CLI.",
    ),
    cursor: bool = typer.Option(
        False,
        "--cursor",
        help="Automatically install to Cursor by modifying ~/.cursor/mcp.json (or equivalent).",
    ),
    opencode: bool = typer.Option(
        False,
        "--opencode",
        help="Automatically install to OpenCode by modifying ~/.config/opencode/opencode.json.",
    ),
    wsl: bool = typer.Option(
        False,
        "--wsl",
        help="Generate WSL-compatible configuration (uses wsl.exe wrapper).",
    ),
):
    """Generate MCP server configuration JSON for agents."""
    if claude_code:
        _install_to_claude_code()
    elif cursor:
        _install_to_cursor()
    elif opencode:
        _install_to_opencode()
    else:
        # Default behavior: show JSON configuration
        if wsl:
            # For WSL, use wsl.exe wrapper to call the entry point
            config = {
                "mcpServers": {
                    "openground": {
                        "command": "wsl.exe",
                        "args": ["openground-mcp"],
                    }
                }
            }
        else:
            mcp_command = _find_openground_mcp_command()
            config = {
                "mcpServers": {
                    "openground": {
                        "command": mcp_command,
                    }
                }
            }

        json_str = json.dumps(config, indent=2)

        # Build ASCII box
        title = " MCP Configuration "
        lines = json_str.split("\n")
        box_width = max(max(len(line) for line in lines), len(title)) + 4

        # Borders
        side_len = (box_width - len(title)) // 2
        top_border = "-" * side_len + title + "-" * side_len
        if len(top_border) < box_width:
            top_border += "-"
        bottom_border = "-" * len(top_border)

        # Print the box
        print()
        print(top_border)
        print()
        print(json_str)
        print()
        print(bottom_border)

        # Instructions
        print()
        print("Copy the JSON above into your MCP configuration file.")
        print(
            "Tip: Run `openground install-mcp --claude-code`, `openground install-mcp --cursor`, or `openground install-mcp --opencode` to automatically install."
        )
        print()


@config_app.command("show")
def config_show(
    defaults: bool = typer.Option(
        False, "--defaults", help="Show only hardcoded defaults (ignore user config)."
    ),
):
    """Display current configuration."""
    config_path = get_config_path()
    print(f"Path to config file: {config_path}\n")

    if defaults:
        # Show hardcoded defaults from source of truth
        config = get_default_config()
        print("Default values:")
        print(json.dumps(config, indent=2))
    else:
        # Show effective config
        config = get_effective_config()
        print(json.dumps(config, indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(
        ..., help="Config key (use dot notation like 'embeddings.chunk_size')"
    ),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a configuration value."""
    # Load current config (not merged with defaults)
    config = load_config()

    # Parse the key (support dot notation)
    parts = key.split(".")

    # Convert value to an appropriate type.
    #
    # Supports JSON literals for booleans, null, arrays, and objects:
    #   openground config set query.top_k 7
    # For plain strings, keep as-is (no quotes needed).
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    # Validate embedding_backend if setting embeddings.embedding_backend
    if key == "embeddings.embedding_backend":
        if parsed_value not in ("sentence-transformers", "fastembed"):
            error(
                f"Error: Invalid value for 'embeddings.embedding_backend': '{parsed_value}'. Must be 'sentence-transformers' or 'fastembed'."
            )
            raise typer.Exit(1)

    # Navigate to the right place in the config (supports arbitrary depth).
    if not parts or any(not p for p in parts):
        error(f"Error: Invalid key format '{key}'.")
        raise typer.Exit(1)

    cur = config
    for part in parts[:-1]:
        existing = cur.get(part)
        if existing is None:
            cur[part] = {}
            existing = cur[part]
        if not isinstance(existing, dict):
            error(
                f"Error: Cannot set '{key}' because '{part}' is not an object in config."
            )
            raise typer.Exit(1)
        cur = existing
    cur[parts[-1]] = parsed_value

    # Save config
    save_config(config)
    clear_config_cache()

    success(f"Set {key} = {parsed_value}")
    print(f"   Config saved to {get_config_path()}")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(
        ..., help="Config key (use dot notation like 'embeddings.chunk_size')"
    ),
):
    """Get a configuration value."""
    config = get_effective_config()

    # Parse the key (support dot notation)
    parts = key.split(".")

    try:
        if not parts or any(not p for p in parts):
            error(f"Error: Invalid key format '{key}'.")
            raise typer.Exit(1)

        cur: object = config
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                raise KeyError(part)
            cur = cur[part]

        print(cur)
    except KeyError:
        error(f"Error: Key '{key}' not found in config.")
        raise typer.Exit(1)


@config_app.command("path")
def config_path():
    """Print the path to the configuration file."""
    print(get_config_path())


@config_app.command("reset")
def config_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Reset configuration to defaults (deletes the config file)."""
    config_path = get_config_path()

    if not config_path.exists():
        print("No config file exists. Nothing to reset.")
        return

    if not yes:
        typer.confirm(f"Delete config file at {config_path}?", abort=True)

    config_path.unlink()
    clear_config_cache()
    success(f"Config file deleted: {config_path}")
    print("   All settings will use defaults.")


def _delete_directory_with_cache(
    path: Path, item_type: str, clear_caches: bool = False
) -> bool:
    """
    Delete a directory with optional cache clearing.

    Args:
        path: Directory path to delete
        item_type: Type of item for success message (e.g., "LanceDB directory", "raw data directory")
        clear_caches: If True, clear query caches after deletion

    Returns:
        True if directory was deleted, False if it didn't exist
    """
    import shutil
    from openground.query import clear_query_caches

    if path.exists():
        shutil.rmtree(path)
        if clear_caches:
            clear_query_caches()
        success(f"Deleted {item_type}: {path}")
        return True
    return False


@nuke_app.command("all")
def nuke_all(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Delete all files in both raw_data and LanceDB directories."""
    from openground.query import list_libraries

    config = get_effective_config()
    raw_data_dir = Path(config["raw_data_dir"]).expanduser()
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    # Count libraries in raw_data
    raw_libraries = []
    if raw_data_dir.exists():
        raw_libraries = [d.name for d in raw_data_dir.iterdir() if d.is_dir()]
    raw_count = len(raw_libraries)

    # Count libraries in embeddings
    embedding_libraries = []
    try:
        embedding_libraries = list_libraries(db_path=db_path, table_name=table_name)
    except Exception:
        # Table might not exist, that's okay
        pass
    embedding_count = len(embedding_libraries)

    # Show summary
    warning("\nThis will permanently delete ALL data:")
    print(f"  • Raw data: {raw_count} libraries in {raw_data_dir}")
    print(f"  • Embeddings: {embedding_count} libraries in {db_path}")
    print()

    if raw_count == 0 and embedding_count == 0:
        print("No data found. Nothing to delete.")
        return

    hint(
        "Tip: Run 'openground list-raw-libraries' and 'openground list-libraries' "
        "to see what will be deleted."
    )
    print()

    if not yes:
        typer.confirm(
            "Are you sure you want to delete ALL data? This cannot be undone!",
            abort=True,
        )

    # Delete raw_data
    _delete_directory_with_cache(raw_data_dir, "raw data directory")

    # Delete db_path
    _delete_directory_with_cache(db_path, "LanceDB directory", clear_caches=True)

    if raw_count > 0 or embedding_count > 0:
        success(
            f"\nDeleted all data ({raw_count} raw libraries, {embedding_count} embedded libraries)."
        )


@nuke_app.command("raw_data")
def nuke_raw_data(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Delete all files in the raw_data directory."""
    config = get_effective_config()
    raw_data_dir = Path(config["raw_data_dir"]).expanduser()

    # Count libraries in raw_data
    raw_libraries = []
    if raw_data_dir.exists():
        raw_libraries = [d.name for d in raw_data_dir.iterdir() if d.is_dir()]
    raw_count = len(raw_libraries)

    # Show summary
    warning("\nThis will permanently delete ALL raw data:")
    print(f"  • {raw_count} libraries in {raw_data_dir}")
    print()

    if raw_count == 0:
        print("No raw data found. Nothing to delete.")
        return

    hint("Tip: Run 'openground list-raw-libraries' to see what will be deleted.")
    print()

    if not yes:
        typer.confirm(
            "Are you sure you want to delete ALL raw data? This cannot be undone!",
            abort=True,
        )

    # Delete raw_data
    if _delete_directory_with_cache(raw_data_dir, "raw data directory"):
        success(f"\nDeleted {raw_count} raw libraries.")


@nuke_app.command("embeddings")
def nuke_embeddings(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Delete all files in the LanceDB directory."""
    from openground.query import list_libraries

    config = get_effective_config()
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    # Count libraries in embeddings
    embedding_libraries = []
    try:
        embedding_libraries = list_libraries(db_path=db_path, table_name=table_name)
    except Exception:
        # Do nothing if table doesn't exist
        pass
    embedding_count = len(embedding_libraries)

    warning("\nThis will permanently delete ALL embeddings:")
    print(f"  • {embedding_count} libraries in {db_path}")
    print()

    if embedding_count == 0:
        print("No embeddings found. Nothing to delete.")
        return

    hint("Tip: Run 'openground list-libraries' to see what will be deleted.")
    print()

    if not yes:
        typer.confirm(
            "Are you sure you want to delete ALL embeddings? This cannot be undone!",
            abort=True,
        )

    # Delete db_path
    if _delete_directory_with_cache(db_path, "LanceDB directory", clear_caches=True):
        success(f"\nDeleted {embedding_count} embedded libraries.")


@stats_app.command("show")
def stats_show():
    """Display openground statistics."""
    from openground.stats import load_stats

    config = get_effective_config()
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    stats = load_stats(db_path=db_path, table_name=table_name)

    print("Openground Statistics")
    print("=" * 50)
    print(f"Libraries: {stats['libraries_count']}")
    print(f"Total chunks: {stats['total_chunks']}")
    print("\nTool calls:")
    for tool_name in sorted(stats["tool_calls"].keys()):
        count = stats["tool_calls"][tool_name]
        print(f"  {tool_name}: {count}")


@stats_app.command("reset")
def stats_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Clear tool call statistics (reset to zero)."""
    from openground.stats import reset_stats

    if not yes:
        typer.confirm(
            "Are you sure you want to clear all tool call statistics?", abort=True
        )

    reset_stats()
    success("Statistics cleared. Tool call counts reset to zero.")


if __name__ == "__main__":
    app()
