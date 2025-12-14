 
# openground

Openground is a system for managing documentation in an agent-friendly manner. It has a CLI to extract and store docs from websites and exposes tools via MCP to agents for querying the data via hybrid BM25 full-text search and vector similarity search.

## Installation

### Basic Installation

```bash
uv pip install -e .
```

This installs the `openground` command entrypoint.

### Installing the MCP server

Openground can be automatically installed to various AI coding agents:

```bash
openground install-mcp                    # displays MCP config JSON that can be copied into your agent's config file
openground install-mcp --opencode         # configures openground in OpenCode's MCP settings (~/.config/opencode/opencode.json)
openground install-mcp --claude-code      # configures openground in Claude Code's MCP settings
openground install-mcp --cursor           # configures openground in Cursor's MCP settings (~/.cursor/mcp.json)
```

## Commands

### Extract

Fetch and parse pages from the sitemap.

```bash
openground extract \
  --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
  --library-name databricks \
  -f docs -f documentation -f blog
```

Flags:
- `--sitemap-url` / `-s`: root sitemap URL.
- `--concurrency-limit` / `-c`: max concurrent requests.
- `--library-name` / `-l`: name of the library/framework for this documentation.
- `--output-dir` / `-o`: where extracted JSON files are written (optional; defaults to `raw_data/{library_name}` based on `--library-name`).
- `--filter-keyword` / `-f`: repeatable; keywords to keep URLs (e.g., `-f docs -f blog`).

### Ingest

Chunk documents, embed, and load into LanceDB.

```bash
openground ingest```

### Query

Hybrid search (semantic + BM25).

```bash
openground query "how to connect" \
  --db-path lancedb_data \
  --table-name documents \
  --top-k 5
```

Optional:
- `--library-name` / `-l`: filter by library name.

## Notes

- Default output dir for extract is `raw_data/{library_name}` (automatically derived from `--library-name`).
- LanceDB data defaults to `.lancedb`; table defaults to `documents`.
- Reinstall (`uv pip install -e .`) after CLI code changes to refresh the entrypoint. 
