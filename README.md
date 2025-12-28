# openground

[![PyPI version](https://badge.fury.io/py/openground.svg)](https://badge.fury.io/py/openground)

Openground is a system for managing your own local RAG pipeline for documentation and allowing your coding agents to query it via MCP. It extracts and embeds contents from git repos and websites, and allows agents to quer it using hybrid BM25 full-text search and vector similarity search.

## Architecture

````
    ┌───────────────────────────────────────────────────────────┐
    │                      OPENGROUND                           │
    └───────────────────────────────────────────────────────────┘

       SOURCE                  PROCESS             STORAGE/OUTPUT

    ┌──────────┐      ┌───────────┐   ┌──────────┐   ┌──────────┐
    │ git repo │─────>│  Extract  │──>│  Chunk   │──>│ LanceDB  │
    |   -or-   |      │ (scrape/  │   │   Text   │   │ (vector  │
    │ sitemap  │      │  clone)   │   └──────────┘   │  +BM25)  │
    └──────────┘      └───────────┘        │         └────┬─────┘
                                           ▼              │
                                    ┌───────────┐         │
                                    │   Local   │─────────┘
                                    │ Embedding │         │
                                    │   Model   │         ▼
                                    └───────────┘  ┌─────────────┐
                                                   │ CLI / MCP   │
                                                   │   (query)   │
                                                   └─────────────┘
```

## Quick Start

### Installation

Recommended to install with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install openground
```

or

```bash
pip install openground
```

### Index Documentation

Openground can source documentation from git repos or sitemaps.

To add documentation from a git repo to openground, run:

```bash
openground add library-name \
  --source https://github.com/example/example.git \
  --docs-path docs/ \
  -y
```

To add documentation from a sitemap to openground, run:

```bash
openground add library-name \
  --source https://docs.example.com/sitemap.xml \
  --filter-keyword docs/ \
  --filter-keyword blog/ \
  -y
```

This will download the docs, embed them, and store them into lancedb. All locally.

### Use with AI Agents

To install the MCP server:

```bash
# For Cursor
openground install-mcp --cursor

# For Claude Code
openground install-mcp --claude-code

# For OpenCode
openground install-mcp --opencode

# For any other agent
openground install-mcp
```

Now your AI assistant can search your stored documentation automatically!

## Example Workflow

Here's how to index the PyTorch documentation and make it available to Claude Code:

```bash
# 1. Install openground
uv tool install openground

# 2. Add pytorch to openground
openground add pytorch --source https://github.com/pytorch/pytorch.git --docs-path docs/ -y

# 3. Configure Claude Code to use openground
openground install-mcp --claude-code

# 4. Restart Claude Code
# Now you can ask: "?"
# Claude will search the Databricks docs automatically!
````

## Development

To contribute or work on openground locally:

```bash
git clone https://github.com/yourusername/openground.git
cd openground
uv sync .
```

## License

MIT
