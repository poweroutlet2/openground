# openground

[![PyPI version](https://badge.fury.io/py/openground.svg)](https://badge.fury.io/py/openground)

Openground is a system for managing documentation in an agent-friendly manner. It extracts and stores docs from websites, then exposes them to AI coding agents via MCP for querying with hybrid BM25 full-text search and vector similarity search.

**[📚 Full Documentation](docs/)**

## Quick Start

### Installation

```bash
pip install openground
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install openground
```

### Index Documentation

Extract and embed documentation in one command:

```bash
openground add \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -y
```

### Query from CLI

```bash
openground query "how to authenticate" --library example-docs
```

### Use with AI Agents

Configure your AI coding assistant to use openground via MCP:

```bash
# For Cursor
openground install-mcp --cursor

# For Claude Code
openground install-mcp --claude-code

# For OpenCode
openground install-mcp --opencode
```

Now your AI assistant can search your documentation automatically!

## Architecture

```
          ┌─────────────────────────────────────────────────────────────────────────────┐
          │                              OPENGROUND                                     │
          ├─────────────────────────────────────────────────────────────────────────────┤
          │                                                                             │
          │  ┌───────────────────────────────────────────────────────────────────────┐  │
          │  │                           EMBEDDING PIPELINE                          │  │
          │  │                                                                       │  │
          │  │                                                                       |  |
          │  │   ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐     │  │
          │  │   │   EXTRACT   │     │    EMBED    │     │    LOCAL LANCEDB    │     │  │
          │  │   │  • Sitemap  │     │  • Chunking │     │  • Vector Store     │     │  │
          │  │   │    Parsing  │────>│  • Local    │────>│  • BM25 FTS Index   │     │  │
          │  │   │  • Web      │     │    Embedding│     │  • Hybrid Search    │     │  │
          │  │   │    Scraping │     │    Model    │     │                     │     │  │
          │  │   └─────────────┘     └─────────────┘     └──────────┬──────────┘     │  │
          │  │         │                    ^                       │                │  │
          │  │         ▼                    |                       │                │  │
          │  │   ┌─────────────┐            |                       │                │  │
          │  │   │     JSON    │ ───────────┘                       │                │  │
          │  │   │             │                                    │                │  │
          │  │   └─────────────┘                                    │                │  │
          │  └──────────────────────────────────────────────────────│────────────────┘  │
          │                                                         │                   │
          │  ┌───────────────────────────────────────────────────── ▼ ───────────────┐  │
          │  │                        QUERY INTERFACE                                │  │
          │  │                                                                       │  │
          │  │   ┌─────────────────────┐      ┌─────────────────────────────────┐    │  │
          │  │   │    CLI COMMANDS     │      │         FASTMCP SERVER          │    │  │
          │  │   │                     │      │                                 │    │  │
          │  │   │  openground query   │      │  • search_documents_tool        │    │  │
          │  │   │  openground ls      │      │  • list_libraries_tool          │    │  │
          │  │   │  openground rm      │      │  • get_full_content_tool        │    │  │
          │  │   │                     │      │                                 │    │  │
          │  │   └─────────────────────┘      └─────────────────────────────────┘    │  │
          │  │            │                                 │                        │  │
          │  └────────────│─────────────────────────────────│────────────────────────┘  │
          │               │                                 │                           │
          └───────────────│─────────────────────────────────│───────────────────────────┘
                          │                                 │
                          ▼                                 ▼
                   ┌────────────┐                  ┌────────────────┐
                   │    USER    │                  │   AI AGENTS    │
                   │  Terminal  │                  │  Cursor/Claude │
                   └────────────┘                  └────────────────┘
```

## Documentation

-   **[Getting Started](docs/docs/getting-started.md)** - Installation and quick start guide
-   **[Configuration](docs/docs/configuration.md)** - Customize chunking, embedding models, and more
-   **[CLI Commands](docs/docs/commands/)** - Complete command reference
-   **[MCP Integration](docs/docs/mcp-integration.md)** - Connect to AI coding assistants

## Features

-   **Extract** documentation from any website with a sitemap
-   **Hybrid search** combining semantic similarity (vector embeddings) and BM25 keyword matching
-   **Local-first** - all processing happens on your machine, no API calls
-   **MCP server** for seamless integration with AI coding assistants
-   **Configurable** chunking, embedding models, and search parameters

## Example Workflow

Here's how to index the Databricks documentation and make it available to Claude Code:

```bash
# 1. Install openground
pip install openground

# 2. Extract and embed Databricks docs
openground add \
  --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
  --library databricks \
  -f docs -f documentation \
  -y

# 3. Configure Claude Code to use openground
openground install-mcp --claude-code

# 4. Restart Claude Code
# Now you can ask: "How do I create a Delta table in Databricks?"
# Claude will search the Databricks docs automatically!
```

## Development

To contribute or work on openground locally:

```bash
git clone https://github.com/yourusername/openground.git
cd openground
uv pip install -e .
```

## License

MIT
