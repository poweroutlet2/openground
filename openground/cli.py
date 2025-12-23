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
)

app = typer.Typer(
    help="Openground is a CLI for storing and querying documentation in a local vector database."
)


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
        print(f"✓ Config file created at {config_path}\n")


@app.command("add")
def add(
    library: str = typer.Option(
        ..., "--library", "-l", help="Name of the library/framework."
    ),
    sitemap_url: str = typer.Option(
        ..., "--sitemap-url", "-s", help="Root sitemap URL to crawl."
    ),
    filter_keywords: list[str] = typer.Option(
        [],
        "--filter-keyword",
        "-f",
        help="Keyword filter applied to sitemap URLs. Can be specified multiple times (e.g., -f docs -f blog).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt between extract and ingest.",
    ),
):
    """Extract pages from a sitemap and ingest them into the local db in one step."""
    from rich.console import Console

    console = Console()
    with console.status("[bold green]"):
        from openground.extract import extract_pages as extract_main
        from openground.ingest import ingest_to_lancedb, load_parsed_pages

    # Get config
    config = get_effective_config()

    # Construct output directory from library
    output_dir = get_library_raw_data_dir(library)

    async def _run_extract():
        await extract_main(
            sitemap_url=sitemap_url,
            concurrency_limit=config["extraction"]["concurrency_limit"],
            library_name=library,
            output_dir=output_dir,
            filter_keywords=filter_keywords,
        )

    asyncio.run(_run_extract())

    data_dir = get_library_raw_data_dir(library)
    if not data_dir.exists():
        raise typer.BadParameter(
            f"Extraction completed but data directory not found at {data_dir}."
        )

    json_files = list(data_dir.glob("*.json"))
    page_count = len(json_files)
    print(f"\n✅ Extraction complete: {page_count} pages extracted to {data_dir}")

    if not yes:
        print("\nPress Enter to continue with ingestion, or Ctrl+C to exit...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n❌ Cancelled by user.")
            raise typer.Abort()

    print("\n🚀 Starting ingestion...")
    pages = load_parsed_pages(data_dir)

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    ingest_to_lancedb(
        pages=pages,
        db_path=db_path,
        table_name=table_name,
        chunk_size=config["ingestion"]["chunk_size"],
        chunk_overlap=config["ingestion"]["chunk_overlap"],
        batch_size=config["ingestion"]["batch_size"],
        embedding_model=config["ingestion"]["embedding_model"],
        embedding_dimensions=config["ingestion"]["embedding_dimensions"],
    )


@app.command()
def extract(
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
        "--filter-keyword",
        "-f",
        help="Keyword filter applied to sitemap URLs. Can be specified multiple times (e.g., -f docs -f blog).",
        show_default=True,
    ),
    concurrency_limit: int | None = typer.Option(
        None,
        "--concurrency-limit",
        "-c",
        help="Maximum number of concurrent requests.",
        min=1,
    ),
):
    """Run the extraction pipeline to fetch and parse pages from a sitemap."""

    from openground.extract import extract_pages as extract_main

    # Get config
    config = get_effective_config()

    # Use CLI flag if provided, otherwise use config value
    if concurrency_limit is None:
        concurrency_limit = config["extraction"]["concurrency_limit"]

    # Output dir is always computed from library
    output_dir = get_library_raw_data_dir(library)

    async def _run():
        await extract_main(
            sitemap_url=sitemap_url,
            concurrency_limit=concurrency_limit,  # type: ignore
            library_name=library,
            output_dir=output_dir,
            filter_keywords=filter_keywords,
        )

    asyncio.run(_run())


@app.command()
def ingest(
    library: Optional[str] = typer.Option(
        None,
        "--library",
        "-l",
        help="Library name to ingest from raw_data/{library}.",
    ),
    batch_size: int | None = typer.Option(
        None,
        "--batch-size",
        "-bs",
        help="Batch size for embedding generation.",
        min=1,
    ),
    chunk_size: int | None = typer.Option(
        None,
        "--chunk-size",
        "-cs",
        help="Chunk size for splitting documents.",
        min=1,
    ),
    chunk_overlap: int | None = typer.Option(
        None,
        "--chunk-overlap",
        "-co",
        help="Overlap size between chunks.",
        min=0,
    ),
):
    """Chunk documents, generate embeddings, and ingest into the local db."""
    from rich.console import Console

    console = Console()
    with console.status("[bold green]"):
        from openground.ingest import ingest_to_lancedb, load_parsed_pages

    # Get config
    config = get_effective_config()

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    # Use CLI flags if provided, otherwise use config values
    if batch_size is None:
        batch_size = config["ingestion"]["batch_size"]
    if chunk_size is None:
        chunk_size = config["ingestion"]["chunk_size"]
    if chunk_overlap is None:
        chunk_overlap = config["ingestion"]["chunk_overlap"]

    # If library is specified, construct the path and validate it exists
    if library:
        data_dir = get_library_raw_data_dir(library)
        if not data_dir.exists():
            raise typer.BadParameter(
                f"Library '{library}' not found at {data_dir}. "
                f"Use 'list-raw-libraries' to see available libraries."
            )
    else:
        # If no library specified, default to the default library name, but still
        # respect config["raw_data_dir"].
        library = DEFAULT_LIBRARY_NAME
        data_dir = get_library_raw_data_dir(library)

    pages = load_parsed_pages(data_dir)
    ingest_to_lancedb(
        pages=pages,
        db_path=db_path,
        table_name=table_name,
        chunk_size=chunk_size,  # type: ignore
        chunk_overlap=chunk_overlap,  # type: ignore
        batch_size=batch_size,  # type: ignore
        embedding_model=config["ingestion"]["embedding_model"],
        embedding_dimensions=config["ingestion"]["embedding_dimensions"],
    )


@app.command("query")
def query_cmd(
    query: str = typer.Argument(..., help="Query string for hybrid search."),
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

    results_md = search(
        query=query,
        db_path=db_path,
        table_name=table_name,
        library_name=library,
        top_k=top_k,  # type: ignore
    )
    print(results_md)


@app.command("list-libraries")
@app.command("ls")
def list_libraries_cmd():
    """List available libraries stored in the local db."""
    from openground.query import list_libraries

    # Get config
    config = get_effective_config()

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    libraries = list_libraries(db_path=db_path, table_name=table_name)
    if not libraries:
        print("No libraries found.")
        return

    for lib in libraries:
        print(lib)


@app.command("list-raw-libraries")
def list_raw_libraries_cmd():
    """List available libraries in the raw_data directory."""
    config = get_effective_config()
    raw_data_dir = Path(config["raw_data_dir"]).expanduser()
    if not raw_data_dir.exists():
        print("No libraries found in raw_data.")
        return

    libraries = [d.name for d in raw_data_dir.iterdir() if d.is_dir()]
    if not libraries:
        print("No libraries found in raw_data.")
        return

    print("Available libraries in raw_data:")
    for lib in sorted(libraries):
        print(f"  - {lib}")


@app.command("remove")
@app.command("rm")
def remove_library_cmd(
    library_name: str = typer.Argument(..., help="Name of the library to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
):
    """Remove all documents for a library from the local db."""
    from openground.query import get_library_stats, delete_library

    # Get config
    config = get_effective_config()

    # Get db_path and table_name from config
    db_path = Path(config["db_path"]).expanduser()
    table_name = config["table_name"]

    stats = get_library_stats(library_name, db_path, table_name)
    if not stats:
        print(f"Library '{library_name}' not found.")
        raise typer.Exit(1)

    # Show confirmation info
    print(f"\nLibrary: {stats['library_name']}")
    print(f"  Chunks: {stats['chunk_count']}")
    print(f"  Pages:  {stats['unique_urls']}")
    if stats["titles"]:
        print(f"  Sample titles: {', '.join(stats['titles'][:3])}")
    else:
        print("  Sample titles: (no titles available)")

    if not yes:
        typer.confirm("\nAre you sure you want to delete this library?", abort=True)

    deleted = delete_library(library_name, db_path, table_name)
    print(f"\n✅ Deleted {deleted} chunks for library '{library_name}'.")

    # Check if raw library directory exists and offer to delete
    if not yes:
        raw_library_dir = get_library_raw_data_dir(library_name)
        if raw_library_dir.exists():
            if typer.confirm(f"\nAlso delete raw files at {raw_library_dir}?"):
                import shutil

                shutil.rmtree(raw_library_dir)
                print(f"✅ Deleted raw library files at {raw_library_dir}.")


def _install_to_claude_code() -> None:
    """Install openground to Claude Code using the claude CLI."""
    try:
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
            print("✅ Successfully installed openground to Claude Code!")
            if result.stdout:
                print(result.stdout)
        else:
            print("❌ Failed to install to Claude Code.")
            if result.stderr:
                print(f"Error: {result.stderr}")
            if result.stdout:
                print(f"Output: {result.stdout}")
            sys.exit(1)

    except FileNotFoundError:
        print("❌ Error: 'claude' CLI not found in PATH.")
        print("\nPlease install Claude Code CLI first:")
        print("  https://code.claude.com/docs/en/cli")
        print("\nAlternatively, you can manually install by running:")
        print("  openground install-mcp")
        print("  (without --claude-code flag)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error installing to Claude Code: {e}")
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
        return Path.home() / ".config" / "cursor" / "mcp.json"


def _get_opencode_config_path() -> Path:
    """Determine the OpenCode config file path."""
    return Path.home() / ".config" / "opencode" / "opencode.json"


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
            print(f"❌ Error: {config_path} contains invalid JSON.")
            print(f"   Parse error: {e}")
            print("\nPlease fix the file manually or delete it to start fresh.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error reading {config_path}: {e}")
            sys.exit(1)

    # Check if openground already exists
    if "openground" in existing_config.get("mcpServers", {}):
        print("⚠️  Warning: 'openground' is already configured in Cursor.")
        print("Current config will be updated.")

    # Create backup before modifying
    if config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.parent / f"{config_path.name}.backup.{timestamp}"
        try:
            import shutil

            shutil.copy2(config_path, backup_path)
            print(f"📦 Created backup: {backup_path}")
        except Exception as e:
            print(f"⚠️  Warning: Could not create backup: {e}")
            print("Proceeding without backup...")

    # Build new config - uses the openground-mcp entry point
    new_server_config = {
        "command": "openground-mcp",
        "args": [],
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
            print(f"❌ Error: Generated configuration is invalid JSON: {e}")
            sys.exit(1)

        # Atomic rename
        if tmp_path:
            tmp_path.replace(config_path)
        print("✅ Successfully installed openground to Cursor!")
        print(f"   Configuration written to: {config_path}")
        print("\n💡 Restart Cursor to apply changes.")

    except PermissionError:
        print(f"❌ Error: Permission denied writing to {config_path}")
        print("   Please check file permissions or run with appropriate privileges.")
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error writing configuration: {e}")
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
            print(f"❌ Error: {config_path} contains invalid JSON.")
            print(f"   Parse error: {e}")
            print("\nPlease fix the file manually or delete it to start fresh.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error reading {config_path}: {e}")
            sys.exit(1)

    # Check if openground already exists
    if "openground" in existing_config.get("mcp", {}):
        print("⚠️  Warning: 'openground' is already configured in OpenCode.")
        print("Current config will be updated.")

    # Create backup before modifying
    if config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.parent / f"{config_path.name}.backup.{timestamp}"
        try:
            import shutil

            shutil.copy2(config_path, backup_path)
            print(f"📦 Created backup: {backup_path}")
        except Exception as e:
            print(f"⚠️  Warning: Could not create backup: {e}")
            print("Proceeding without backup...")

    # Build new config - uses the openground-mcp entry point
    new_server_config = {
        "type": "local",
        "command": ["openground-mcp"],
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
            print(f"❌ Error: Generated configuration is invalid JSON: {e}")
            sys.exit(1)

        # Atomic rename
        if tmp_path:
            tmp_path.replace(config_path)
        print("✅ Successfully installed openground to OpenCode!")
        print(f"   Configuration written to: {config_path}")
        print("\n💡 Restart OpenCode to apply changes.")

    except PermissionError:
        print(f"❌ Error: Permission denied writing to {config_path}")
        print("   Please check file permissions or run with appropriate privileges.")
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()  # Clean up temp file
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error writing configuration: {e}")
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
            config = {
                "mcpServers": {
                    "openground": {
                        "command": "openground-mcp",
                        "args": [],
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


# Config Sub App
config_app = typer.Typer(help="Manage openground configuration.")
app.add_typer(config_app, name="config")


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
        ..., help="Config key (use dot notation like 'ingestion.chunk_size')"
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
    #   openground config set extraction.enabled true
    #   openground config set query.filters '["docs","api"]'
    # For plain strings, keep as-is (no quotes needed).
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    # Navigate to the right place in the config (supports arbitrary depth).
    if not parts or any(not p for p in parts):
        print(f"❌ Error: Invalid key format '{key}'.")
        raise typer.Exit(1)

    cur = config
    for part in parts[:-1]:
        existing = cur.get(part)
        if existing is None:
            cur[part] = {}
            existing = cur[part]
        if not isinstance(existing, dict):
            print(
                f"❌ Error: Cannot set '{key}' because '{part}' is not an object in config."
            )
            raise typer.Exit(1)
        cur = existing
    cur[parts[-1]] = parsed_value

    # Save config
    save_config(config)
    clear_config_cache()

    print(f"✅ Set {key} = {parsed_value}")
    print(f"   Config saved to {get_config_path()}")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(
        ..., help="Config key (use dot notation like 'ingestion.chunk_size')"
    ),
):
    """Get a configuration value."""
    config = get_effective_config()

    # Parse the key (support dot notation)
    parts = key.split(".")

    try:
        if not parts or any(not p for p in parts):
            print(f"❌ Error: Invalid key format '{key}'.")
            raise typer.Exit(1)

        cur: object = config
        for part in parts:
            if not isinstance(cur, dict) or part not in cur:
                raise KeyError(part)
            cur = cur[part]

        print(cur)
    except KeyError:
        print(f"❌ Error: Key '{key}' not found in config.")
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
    print(f"✅ Config file deleted: {config_path}")
    print("   All settings will use defaults.")


if __name__ == "__main__":
    app()
