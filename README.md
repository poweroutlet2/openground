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
  --library-name example-docs \
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
  --library-name example-docs \
  -y
```

3. **Query** the documentation:

```bash
openground query "how to authenticate" --library-name example-docs
```

4. **Use from AI agents** - once the MCP server is configured, your AI coding assistant can query the documentation automatically.

## Commands

### extract

Fetch and parse pages from a sitemap.

```bash
openground extract \
  --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
  --library-name databricks \
  -f docs -f documentation
```

Flags:
- `--sitemap-url` / `-s`: root sitemap URL
- `--library-name` / `-l`: name of the library/framework
- `--filter-keyword` / `-f`: repeatable; keywords to filter URLs (e.g., `-f docs -f blog`)
- `--concurrency-limit` / `-c`: max concurrent requests (default: 50)
- `--output-dir` / `-o`: custom output directory (defaults to data home)

### ingest

Chunk documents, embed, and load into LanceDB.

```bash
openground ingest --library databricks
```

### query

Hybrid search (semantic + BM25).

```bash
openground query "how to connect" --library-name databricks --top-k 5
```

### list-libraries / ls

List all ingested libraries:

```bash
openground ls
```

### remove-library / rm

Remove a library from the database:

```bash
openground rm databricks
```

## Data Storage

Openground stores data in a platform-appropriate location:

- **Linux/macOS**: `~/.local/share/openground/`
- **Windows**: `~/AppData/Local/openground/`

You can override this by setting the `XDG_DATA_HOME` environment variable.

## Development

```bash
git clone https://github.com/yourusername/openground.git
cd openground
uv pip install -e .
```

## License

MIT
