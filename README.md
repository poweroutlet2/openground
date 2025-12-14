# openground

Openground is a system for managing documentation in an agent-friendly manner. It has a CLI to extract and store docs from websites and exposes tools via MCP to AI coding agents for querying the data via hybrid BM25 full-text search and vector similarity search.

## Installation

Install from PyPI:

```bash
pip install openground
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install openground
```

This installs two commands:
- `openground` - the main CLI for managing documentation
- `openground-mcp` - the MCP server for AI agents

### Installing the MCP Server

After installation, configure your AI coding agent to use openground:

```bash
openground install-mcp                    # displays MCP config JSON to copy into your config
openground install-mcp --cursor           # auto-configures Cursor
openground install-mcp --claude-code      # auto-configures Claude Code
openground install-mcp --opencode         # auto-configures OpenCode
```

## Quick Start

1. **Extract documentation** from a website's sitemap:

```bash
openground extract \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f docs -f guide
```

2. **Ingest** the extracted docs into the vector database:

```bash
openground ingest --library example-docs
```

Or do both in one step:

```bash
openground extract-and-ingest \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -y
```

3. **Query** the documentation:

```bash
openground query "how to authenticate" --library example-docs
```

4. **Use from AI agents** - once the MCP server is configured, your AI coding assistant can query the documentation automatically.

## Configuration

Openground uses a JSON configuration file to store persistent settings. The config file is located at:

- **Linux/macOS**: `~/.config/openground/config.json`
- **Windows**: `~/AppData/Local/openground/config.json`

You can override this by setting the `XDG_CONFIG_HOME` environment variable.

### Default Configuration

By default, openground uses sensible defaults. You can view the current effective configuration:

```bash
openground config show
```

### Managing Configuration

The openground config will get created automatically if it doesn't exist on any command call. You can change config values like so:

Set configuration values:

```bash
openground config set db_path ~/custom/path/to/lancedb
openground config set ingestion.chunk_size 1500
openground config set query.top_k 10
```

Get a specific value:

```bash
openground config get db_path
openground config get ingestion.chunk_size
```

View the config file location:

```bash
openground config path
```

Reset to defaults (deletes config file):

```bash
openground config reset
```

### Configuration Schema

```json
{
  "db_path": "~/.local/share/openground/lancedb",
  "table_name": "documents",
  "extraction": {
    "concurrency_limit": 50
  },
  "ingestion": {
    "batch_size": 32,
    "chunk_size": 1000,
    "chunk_overlap": 200
  },
  "query": {
    "top_k": 5
  },
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_dimensions": 384
}
```

### Configuration Precedence

For options that support CLI flags, precedence is:

1. CLI flag (highest priority)
2. Config file value
3. Hardcoded default (lowest priority)

Note: Path-related options (`db_path`, `table_name`, `output_dir`, `data_dir`) and embedding configuration (`embedding_model`, `embedding_dimensions`) are **only** configurable via the config file and cannot be overridden with CLI flags.

## Commands

### extract

Fetch and parse pages from a sitemap.

```bash
openground extract \
  --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
  --library databricks \
  -f docs -f documentation
```

Flags:
- `--sitemap-url` / `-s`: root sitemap URL
- `--library` / `-l`: name of the library/framework
- `--filter-keyword` / `-f`: repeatable; keywords to filter URLs (e.g., `-f docs -f blog`)
- `--concurrency-limit` / `-c`: max concurrent requests (defaults to config value or 50)

The output directory is automatically determined from the library name and stored in the data home directory.

### ingest

Chunk documents, embed, and load into LanceDB.

```bash
openground ingest --library databricks
```

Flags:
- `--library` / `-l`: library name to ingest from `raw_data/{library}`
- `--batch-size` / `-bs`: batch size for embedding generation (defaults to config value or 32)
- `--chunk-size` / `-cs`: chunk size for splitting documents (defaults to config value or 1000)
- `--chunk-overlap` / `-co`: overlap size between chunks (defaults to config value or 200)

The database path and table name are configured via the config file (see Configuration section).

### query

Hybrid search (semantic + BM25).

```bash
openground query "how to connect" --library databricks --top-k 5
```

Flags:
- `query`: the search query (required positional argument)
- `--library` / `-l`: optional library name filter
- `--top-k` / `-k`: number of results to return (defaults to config value or 5)

The database path and table name are configured via the config file (see Configuration section).

### list-libraries / ls

List all ingested libraries:

```bash
openground ls
```

The database path and table name are configured via the config file.

### remove-library / rm

Remove a library from the database:

```bash
openground rm databricks
```

Flags:
- `library`: name of the library to remove (required positional argument)
- `--yes` / `-y`: skip confirmation prompt

The database path and table name are configured via the config file.

### config

Manage openground configuration.

```bash
openground config show              # Display current effective config
openground config set <key> <value> # Set a value (dot notation: "ingestion.chunk_size")
openground config get <key>         # Get a specific value
openground config path              # Print config file location
openground config reset             # Reset to defaults (delete file)
```

## Data Storage

Openground stores data in a platform-appropriate location:

- **Linux/macOS**: `~/.local/share/openground/`
- **Windows**: `~/AppData/Local/openground/`

You can override this by setting the `XDG_DATA_HOME` environment variable.

The database path can be customized via the configuration file (see Configuration section).

## Development

```bash
git clone https://github.com/yourusername/openground.git
cd openground
uv pip install -e .
```

## License

MIT
