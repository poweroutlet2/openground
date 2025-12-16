# Getting Started

This guide will help you install openground and get your first documentation library indexed and searchable.

## Installation

### Using pip

```bash
pip install openground
```

### Using uv (recommended)

[uv](https://docs.astral.sh/uv/) is a fast Python package installer. If you have it installed:

```bash
uv tool install openground
```

### Verify Installation

After installation, you should have two commands available:

```bash
openground --help       # Main CLI for managing documentation
openground-mcp --help   # MCP server for AI agents
```

## Quick Start

Let's walk through indexing documentation from a website and querying it.

### Option 1: Extract and Ingest in One Step

The fastest way to get started is with the combined command:

```bash
openground extract-and-ingest \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -y
```

This will:

1. Extract all pages from the sitemap
2. Save them as JSON in your data directory
3. Chunk and embed the content
4. Store everything in LanceDB for searching

!!! tip "Filtering URLs"
    Add `-f` flags to only extract URLs containing specific keywords:
    ```bash
    openground extract-and-ingest \
      --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
      --library databricks \
      -f docs -f guide \
      -y
    ```

### Option 2: Extract and Ingest Separately

For more control, you can split the process into two steps:

#### Step 1: Extract Documentation

```bash
openground extract \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f docs -f guide
```

This downloads and parses all documentation pages, saving them as JSON files in `~/.local/share/openground/raw_data/example-docs/`.

#### Step 2: Ingest into Database

```bash
openground ingest --library example-docs
```

This processes the JSON files and loads them into the vector database at `~/.local/share/openground/lancedb/`.

!!! note "Why separate steps?"
    Separating extraction and ingestion lets you:
    
    - Extract once, re-ingest with different chunking strategies
    - Review extracted content before indexing
    - Keep raw data for backup or analysis

### Query Your Documentation

Once ingested, you can search your documentation:

```bash
openground query "how to authenticate" --library example-docs
```

Output example:

```
Results for: "how to authenticate"

1. Authentication Guide (Score: 0.85)
   Library: example-docs
   URL: https://docs.example.com/guides/authentication
   
   To authenticate with the API, you need to obtain an API key from your dashboard...

2. API Keys (Score: 0.78)
   Library: example-docs
   URL: https://docs.example.com/api/keys
   
   API keys are used to authenticate requests to the API. You can create keys in the...
```

### List Your Libraries

See all indexed documentation libraries:

```bash
openground ls
```

### Remove a Library

To delete a library from the database:

```bash
openground rm example-docs
```

You'll be prompted for confirmation unless you pass `-y`:

```bash
openground rm example-docs -y
```

## Installing the MCP Server

To use openground with AI coding assistants like Cursor or Claude, install the MCP server:

```bash
# Auto-configure for Cursor
openground install-mcp --cursor

# Auto-configure for Claude Code
openground install-mcp --claude-code

# Auto-configure for OpenCode
openground install-mcp --opencode

# Just show the config (copy manually)
openground install-mcp
```

For more details, see the [MCP Integration](mcp-integration.md) guide.

## Next Steps

- [Configuration](configuration.md) - Customize chunking, embedding models, and more
- [Commands](commands/index.md) - Explore all available commands
- [MCP Integration](mcp-integration.md) - Connect to AI agents

## Troubleshooting

### Command Not Found

If `openground` is not found after installation:

- **pip users**: Ensure your Python scripts directory is in PATH
- **uv users**: Ensure `~/.local/bin` is in PATH

### Extraction Fails

If extraction times out or fails:

- Try reducing `--concurrency-limit`: `openground extract -s URL -l NAME -c 10`
- Check that the sitemap URL is valid and accessible
- Some sites may block automated scraping

### Slow Ingestion

First-time ingestion downloads the embedding model (`sentence-transformers/all-MiniLM-L6-v2` by default). Subsequent runs will be faster.

You can adjust batch size to trade off speed vs memory:

```bash
openground ingest --library NAME --batch-size 16  # Smaller batches, less memory
```

