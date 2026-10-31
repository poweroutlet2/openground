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
uv tool install 'openground[fastembed-cpu]'   # also installs fastembed (or fastembed-gpu)
```

fastembed is optional; select it with `"embedding_backend": "fastembed"` in the config file below.

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

`add` adds; `update` refreshes. Each library has one source, remembered in `sources.json` next to the config file, and `openground update` re-extracts every stored version of every library from it (`update NAME` for one), re-embedding only pages that changed. Use `add NAME -v VERSION` to add another version from the same source. `add NAME SOURCE` with a different source than the one a stored library uses is an error: `rm` the library or pick another name. Adding a name and version that is already stored updates it in place.

### Commands

| Command | |
|---|---|
| `add NAME [SOURCE]` | Add a library or another version of it (an existing name+version is updated in place). Without `SOURCE`, reuses the remembered one; without `-v` it will not create a second default version, use `update`. Options (each only valid for its source type): `-d/--docs-path` (git, repeatable), `-v/--version` (git tag or branch), `-f/--filter` (sitemap, repeatable) |
| `update [NAME]` | Refresh libraries from their remembered sources (all if no name) |
| `ls` | List libraries, versions, and whether a source is remembered |
| `rm NAME` | Delete a library version; the remembered source is forgotten once the last version is gone. `-v` is only needed when several versions are stored. `-y` skips the prompt |
| `search QUERY` | Hybrid search from the terminal. Options: `-l`, `-v`, `-k` |
| `serve` | Run the MCP server on stdio (same as `openground-mcp`) |
| `install-mcp [CLIENT]` | Configure `claude-code`, `cursor` or `opencode`; no client prints the JSON. `--wsl` launches the server through `wsl.exe` |
| `config` | Show the config file path, effective settings and data locations |
| `stats` | Library and chunk counts plus MCP tool call counts. `--reset` zeroes the call counts |
| `reset` | Delete embeddings, raw files and stats; config and remembered sources are kept. `-y` skips the prompt |

### Use with AI agents

```bash
openground install-mcp claude-code   # or cursor, opencode
openground install-mcp               # print JSON for any other client
```

Then ask your agent something like "What models are available in fastembed?" and it will search your local docs.

## Configuration

Defaults work out of the box. To change them, create `config.json` in the config directory: `$XDG_CONFIG_HOME/openground` if set, otherwise `~/.config/openground` (Linux/macOS) or `%USERPROFILE%\AppData\Roaming\openground` (Windows). Every key is optional:

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

`embedding_backend` is `sentence-transformers` or `fastembed`. `embedding_dimensions` can be omitted (or `0`) for the common bge and MiniLM models, where it is filled in automatically and a different value is rejected; set it yourself for any other model. Unknown keys are rejected, `chunk_size`, `batch_size` and `top_k` must be positive, and `chunk_overlap` (may be `0`) must be smaller than `chunk_size`. Delete the file to reset.

Embeddings are tied to the backend and model they were made with. If you change them after libraries are stored, openground refuses to add or search until you restore the old values or run `openground reset` and re-add your libraries. Data lives in `$XDG_DATA_HOME/openground` or `~/.local/share/openground` (`%USERPROFILE%\AppData\Local\openground` on Windows); run `openground config` to see all paths.

## Upgrading from 0.14

- **Config is flat.** The old nested `config.json` (`embeddings`, `query`, `extraction`, `sources`, `db_path`, `table_name`, ...) is rejected with an error. Delete it (or rewrite it in the flat format above); `db_path`, `raw_data_dir` and `table_name` are no longer settings.
- **One sources file.** Sources live in `sources.json` next to `config.json`, one source per library. `~/.openground/sources.json`, project-level `.openground/sources.json`, `--sources-file` and the bundled catalog are gone; copy any entries you want to keep. On Windows the config directory moved from `Local` to `Roaming` AppData.
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
