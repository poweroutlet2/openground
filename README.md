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
      │    │   -or-   │                           │         └────┬─────┘    │
      │    │ local dir│                           │              │          │
      │    └──────────┘                           │              │          │
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

### Install

```bash
uv tool install openground                    # sentence-transformers (GPU/MPS/CPU)
uv tool install 'openground[fastembed-cpu]'   # adds the fastembed backend
```

or `pip install openground`.

### Add documentation

`openground add NAME SOURCE` figures out the source type from `SOURCE`:

```bash
# git repo (optionally a docs folder and a tag/branch)
openground add fastembed https://github.com/qdrant/fastembed.git -d docs -v v0.7.4

# sitemap (optionally only URLs containing a keyword)
openground add claude-code https://code.claude.com/docs/sitemap.xml -f /en/

# local directory
openground add my-docs ./docs
```

Git and local sources index `.md`, `.rst`, `.txt`, `.mdx`, `.ipynb`, `.html` and `.htm` files. GitHub/GitLab web URLs like `https://github.com/o/r/tree/v1.0/docs` also work; the tag and folder are picked up from the URL.

openground remembers `SOURCE` in `~/.openground/sources.json`, so later you can run `openground add NAME` (re-extracts and updates only the pages that changed) or `openground update` (refresh everything).

### Commands

| Command | |
|---|---|
| `add NAME [SOURCE]` | Extract and embed a library; re-running updates it. Options: `-d/--docs-path` (git, repeatable), `-v/--version` (git tag or branch), `-f/--filter` (sitemap, repeatable) |
| `update [NAME]` | Refresh libraries from their remembered sources (all if no name) |
| `ls` | List libraries, versions, and whether a source is remembered |
| `rm NAME` | Delete a library version and forget its source. `-v` is only needed when several versions are stored. `-y` skips the prompt |
| `search QUERY` | Hybrid search from the terminal. Options: `-l`, `-v`, `-k` |
| `serve` | Run the MCP server on stdio (same as `openground-mcp`) |
| `install-mcp [CLIENT]` | Configure `claude-code`, `cursor` or `opencode`; no client prints the JSON. `--wsl` launches the server through `wsl.exe` |
| `config` | Show the config file path, effective settings and data locations |
| `stats` | MCP tool call counts. `--reset` zeroes them |
| `reset` | Delete all local data (embeddings, raw files, stats). `-y` skips the prompt |

### Use with AI agents

```bash
openground install-mcp claude-code   # or cursor, opencode
openground install-mcp               # print JSON for any other client
```

Then ask your agent something like "What models are available in fastembed?" and it will search your local docs.

## Configuration

Defaults work out of the box. To change them, create `~/.config/openground/config.json` (`$XDG_CONFIG_HOME/openground/config.json` if set). Every key is optional:

```json
{
  "embedding_backend": "sentence-transformers",
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "embedding_dimensions": 384,
  "batch_size": 32,
  "chunk_size": 800,
  "chunk_overlap": 200,
  "top_k": 5
}
```

`embedding_backend` is `sentence-transformers` or `fastembed`. `embedding_dimensions` is filled in for common bge and MiniLM models; set it yourself for any other model. Unknown keys are rejected. Delete the file to reset.

Changing the backend or model after libraries are stored requires `openground reset` and re-adding them. Data lives in `~/.local/share/openground` (`$XDG_DATA_HOME/openground`); run `openground config` to see all paths.

## Claude Code Agent

Openground includes a custom Claude Code agent that searches official documentation without polluting your main conversation context. See [docs/claude-code-agent.md](docs/claude-code-agent.md) for installation and usage instructions.

## Development

To contribute or work on openground locally:

```bash
git clone https://github.com/poweroutlet2/openground.git
cd openground
uv sync .
```

## License

MIT
