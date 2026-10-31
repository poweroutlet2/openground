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

openground remembers `SOURCE` in `sources.json` next to the config file. Then `openground update` refreshes every stored version of every library from its remembered source (`update NAME` for one library), re-embedding only pages that changed. `openground add NAME` re-adds with the remembered source; if that exact name and version is already stored it is updated incrementally instead.

### Commands

| Command | |
|---|---|
| `add NAME [SOURCE]` | Add a library (an existing name+version is updated in place). Options (each only valid for its source type): `-d/--docs-path` (git, repeatable), `-v/--version` (git tag or branch), `-f/--filter` (sitemap, repeatable) |
| `update [NAME]` | Refresh libraries from their remembered sources (all if no name) |
| `ls` | List libraries, versions, and whether a source is remembered |
| `rm NAME` | Delete a library version; the remembered source is forgotten once the last version is gone. `-v` is only needed when several versions are stored. `-y` skips the prompt |
| `search QUERY` | Hybrid search from the terminal. Options: `-l`, `-v`, `-k` |
| `serve` | Run the MCP server on stdio (same as `openground-mcp`) |
| `install-mcp [CLIENT]` | Configure `claude-code`, `cursor` or `opencode`; no client prints the JSON. `--wsl` launches the server through `wsl.exe` |
| `config` | Show the config file path, effective settings and data locations |
| `stats` | MCP tool call counts. `--reset` zeroes them |
| `reset` | Delete all local data (embeddings, raw files, stats); remembered sources are kept. `-y` skips the prompt |

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

`embedding_backend` is `sentence-transformers` or `fastembed`. `embedding_dimensions` is filled in for common bge and MiniLM models; set it yourself for any other model. Unknown keys and non-positive numbers are rejected, and `chunk_overlap` must be smaller than `chunk_size`. Delete the file to reset.

Embeddings are tied to the backend and model they were made with. If you change them after libraries are stored, openground refuses to add or search until you restore the old values or run `openground reset` and re-add your libraries. Data lives in `~/.local/share/openground` (`$XDG_DATA_HOME/openground`); run `openground config` to see all paths.

## Upgrading from 0.14

- **Config is flat.** The old nested `config.json` (`embeddings`, `query`, `extraction`, `sources`, `db_path`, `table_name`, ...) is rejected with an error. Delete it (or rewrite it in the flat format above); `db_path`, `raw_data_dir` and `table_name` are no longer settings.
- **One sources file.** Sources live in `sources.json` next to `config.json` (`~/.config/openground/sources.json`). `~/.openground/sources.json`, project-level `.openground/sources.json`, `--sources-file` and the bundled catalog are gone; copy any entries you want to keep.
- **Default backend is `sentence-transformers`** (it was `fastembed`). If your existing libraries were embedded with fastembed, either set `"embedding_backend": "fastembed"` in `config.json` or run `openground reset` and re-add them.
- **Commands changed.** `extract-*`, `embed`, `query`, `list-libraries`, `remove`, `nuke`, `config set|get|show|reset` and `stats show|clear` are replaced by the commands above. Local directories are now stored under the version `latest`.

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
