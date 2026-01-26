# openground

[![PyPI version](https://img.shields.io/pypi/v/openground?logo=pypi)](https://pypi.org/project/openground/)

tldr: openground lets you give controlled access to documentation to AI agents. Everything happens on-device.

openground is an on-device RAG system that extracts documentation from git repos and sitemaps, embeds it for semantic search, and exposes it to AI agents via MCP. It uses a local embedding model, and local lancedb for storing embeddings and for hybrid vector similarity and BM25 full-text search.

## Architecture

```
      ┌─────────────────────────────────────────────────────────────────────┐
      │                           OPENGROUND                                │
      ├─────────────────────────────────────────────────────────────────────┤
      │                                                                     │
      │       SOURCE                  PROCESS              STORAGE/CLIENT   │
      │                                                                     │
      │    ┌──────────┐      ┌───────────┐   ┌──────────┐   ┌──────────┐    │
      │    │ git repo ├─────>│  Extract  ├──>│  Chunk   ├──>│ LanceDB  │    │
      │    |   -or-   |      │ (raw_data)│   │   Text   │   │ (vector  │    │
      │    │ sitemap  │      └───────────┘   └──────────┘   │  +BM25)  │    │
      │    └──────────┘                           │         └────┬─────┘    │
      │                                           ▼              │          │
      │                                    ┌───────────┐         │          │
      │                                    │   Local   |<────────┘          │
      │                                    │ Embedding │         │          │
      │                                    │   Model   │         ▼          │
      │                                    └───────────┘  ┌─────────────┐   │
      │                                                   │ CLI / MCP   │   │
      │                                                   │  (hybrid    │   │
      |                                                   |   search)   |   |
      │                                                   └─────────────┘   │
      │                                                                     │
      └─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Installation

Recommended to install with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install openground # Larger package size, automatic GPU/MPS support
uv tool install 'openground[fastembed]' # Lightweight CPU embedding
uv tool install 'openground[fastembed-gpu]' # Experimental CUDA/GPU support through fastembed
```

or

```bash
pip install openground
```

### Add Documentation

Openground can source documentation from git repos or sitemaps.

To add documentation from a git repo to openground, run:

```bash
openground add library-name \
  --source https://github.com/example/example.git \
  --docs-path docs/ \
  --version v1.0.0 \
  -y
```

The `--version` flag specifies a git tag to checkout (defaults to latest).

To add documentation from a sitemap to openground, run:

```bash
openground add library-name \
  --source https://docs.example.com/sitemap.xml \
  --filter-keyword docs/ \
  --filter-keyword blog/ \
  -y
```

This will download the docs, embed them, and store them into lancedb. All locally.

Multiple versions of the same library can be stored and queried independently.

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

Here's how to add the fastembed documentation and make it available to Claude Code:

```bash
# 1. Install openground
uv tool install openground

# 2. Add fastembed to openground
openground add fastembed --source https://github.com/qdrant/fastembed.git --docs-path docs/ --version v0.7.4 -y

# 3. Configure Claude Code to use openground MCP
openground install-mcp --claude-code

# 4. Restart Claude Code
# Now you can ask: "What models are available in fastembed?"
# Claude will search the fastembed docs automatically!
```

## Claude Code Agent

Openground includes a custom Claude Code agent that searches official documentation without polluting your main conversation context. See [docs/claude-code-agent.md](docs/claude-code-agent.md) for installation and usage instructions.

## MCP Usage Statistics
To see how many times each tool in the MCP server has been called:

```bash
openground stats show # show stats
openground stats clear # reset stats
```
## Development

To contribute or work on openground locally:

```bash
git clone https://github.com/poweroutlet2/openground.git
cd openground
uv sync .
```

## License

MIT
