# openground

[![PyPI version](https://img.shields.io/pypi/v/openground?logo=pypi)](https://pypi.org/project/openground/)

On-device RAG for AI coding agents. Feed it documentation from git repos,
sitemaps, or local directories — it embeds everything locally and exposes
a search interface to your AI assistant via MCP.

Nothing leaves your machine.

## Contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Adding Documentation](#adding-documentation)
- [Connecting to AI Agents](#connecting-to-ai-agents)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Data Storage](#data-storage)
- [MCP Tools](#mcp-tools)
- [Development](#development)

---

## How it works

```
  SOURCE              PROCESS                   STORAGE
  ──────              ───────                   ───────

  git repo  ─┐
  sitemap   ─┼──► Extract text ──► Chunk ──► Embed ──► LanceDB
  local dir ─┘       (raw_data)              (local     (vector +
                                              model)     BM25 FTS)
                                                            │
                                                            ▼
                                                     CLI / MCP server
                                                     (hybrid search)
```

1. **Extract** — pull content from a git repo (sparse checkout), crawl a
   sitemap, or read a local directory. Raw pages are saved as JSON under
   `~/.local/share/openground/raw_data/`.

2. **Chunk** — split each page into overlapping segments (default 800 chars,
   200 overlap) using a recursive character splitter.

3. **Embed** — run each chunk through a local embedding model
   (`BAAI/bge-small-en-v1.5`, 384 dimensions). Two backends are available —
   see [Installation](#installation).

4. **Store** — write vectors + full text into a local LanceDB table at
   `~/.local/share/openground/lancedb/`. LanceDB also maintains a BM25
   full-text index on the chunk content.

5. **Search** — queries use hybrid retrieval: dense vector similarity plus
   BM25, re-ranked and returned as markdown snippets. The MCP server exposes
   this to any compatible AI agent.

---

## Installation

Requires **Python 3.10–3.12**. Install with
[uv](https://docs.astral.sh/uv/) (recommended):

```bash
# Full install — sentence-transformers + PyTorch, automatic GPU/MPS/CPU
uv tool install openground

# Lightweight CPU — fastembed (ONNX Runtime), smaller footprint
uv tool install 'openground[fastembed-cpu]'

# Experimental GPU — fastembed with CUDA via ONNX Runtime
uv tool install 'openground[fastembed-gpu]'
```

Or with pip:

```bash
pip install openground
```

### Which variant should I use?

| Variant           | Backend               | GPU support         | Size    |
|-------------------|-----------------------|---------------------|---------|
| base              | sentence-transformers | Auto (CUDA/MPS/CPU) | ~1 GB   |
| `fastembed-cpu`   | ONNX Runtime (CPU)    | None                | ~300 MB |
| `fastembed-gpu`   | ONNX Runtime (CUDA)   | NVIDIA only         | ~500 MB |

If you just want fast local search on a laptop, `fastembed-cpu` is the
right choice. The base install is better if you have a GPU or need
flexibility around the embedding model.

> **Base install note:** the default `embedding_backend` config value is
> `"fastembed"`, but the base install does not include fastembed. If you
> used `uv tool install openground` (no extra), set the backend to
> `sentence-transformers` before ingesting anything:
> ```bash
> openground config set embeddings.embedding_backend sentence-transformers
> ```

---

## Quick Start

```bash
# 1. Add documentation from a git repo
openground add mylib \
  --source https://github.com/example/mylib.git \
  --docs-path docs/ \
  -y

# 2. Register the MCP server with Claude Code
openground install-mcp --claude-code

# 3. Restart Claude Code — it can now search mylib docs automatically
```

---

## Adding Documentation

### From a git repo

```bash
openground add library-name \
  --source https://github.com/example/example.git \
  --docs-path docs/ \
  --version v1.0.0 \   # pin to a git tag; defaults to HEAD
  -y
```

`--docs-path` can be specified multiple times to include several directories.
Supported file types: `.md`, `.rst`, `.txt`, `.mdx`, `.ipynb`, `.html`, `.htm`.

### From a sitemap

```bash
openground add library-name \
  --source https://docs.example.com/sitemap.xml \
  --filter-keyword docs \
  --filter-keyword api \
  -y
```

`--filter-keyword` filters the sitemap URLs to those containing the keyword.
Multiple keywords are OR'd together.

### From a local directory

```bash
openground add library-name --source ./docs -y
openground add library-name --source ~/path/to/docs -y
openground add library-name --source /absolute/path -y
```

Local additions automatically version themselves as `local-YYYY-MM-DD`.

### Updating documentation

```bash
# Update to latest
openground update library-name

# Update to a specific version
openground update library-name --version v2.0.0
```

Updates are incremental: openground hashes each page and only re-embeds
what changed.

### Multiple versions

You can store multiple versions of the same library side by side:

```bash
openground add mylib --source https://github.com/x/mylib.git --version v1.0.0 -y
openground add mylib --source https://github.com/x/mylib.git --version v2.0.0 -y
```

Search against a specific version with `openground query --version v1.0.0`.

---

## Sources Files

When you add a library with `--source`, openground saves the source config
so you can refer to the library by name in future (no need to repeat the URL).

**Two locations:**

| File                         | Scope                                     |
|------------------------------|-------------------------------------------|
| `~/.openground/sources.json` | User-wide, shared across all projects     |
| `.openground/sources.json`   | Project-local, overrides the user file    |

**Lookup order:** CLI `--sources-file` flag → project-local → user home →
package-bundled defaults.

**Format:**

```json
{
  "fastapi": {
    "type": "git_repo",
    "repo_url": "https://github.com/tiangolo/fastapi",
    "docs_paths": ["docs"]
  },
  "numpy": {
    "type": "sitemap",
    "sitemap_url": "https://numpy.org/doc/sitemap.xml",
    "filter_keywords": ["docs/"]
  }
}
```

To stop openground from auto-saving sources:

```bash
openground config set sources.auto_add_local false
```

---

## Connecting to AI Agents

### Claude Code

```bash
openground install-mcp --claude-code
```

This runs two `claude mcp` commands under the hood:

```bash
claude mcp remove openground --scope user          # clean up old entry
claude mcp add --transport stdio --scope user openground -- openground-mcp
```

The `openground-mcp` binary is registered as a user-scoped stdio MCP server.
Requires the `claude` CLI to be in your PATH. After running, restart
Claude Code for the server to load.

### Cursor

```bash
openground install-mcp --cursor
```

Writes an `openground` entry into `~/.cursor/mcp.json`, preserving any
existing entries.

### OpenCode

```bash
openground install-mcp --opencode
```

Writes into `~/.config/opencode/opencode.json`.

### Manual / other agents

```bash
openground install-mcp
```

Prints the MCP server JSON config block to stdout. Copy it into your
agent's MCP config file:

```json
{
  "mcpServers": {
    "openground": {
      "command": "openground-mcp"
    }
  }
}
```

---

## CLI Reference

### Core commands

| Command                    | Description                                    |
|----------------------------|------------------------------------------------|
| `openground add`           | Extract + embed documentation                  |
| `openground update`        | Re-extract + incrementally re-embed            |
| `openground remove`        | Remove a library from LanceDB                  |
| `openground query`         | Run a hybrid search query                      |
| `openground list-libraries`| List all indexed libraries and versions        |
| `openground install-mcp`   | Register the MCP server with an AI agent       |
| `openground version`       | Print the installed version                    |

### `openground add` options

| Flag                    | Description                                         |
|-------------------------|-----------------------------------------------------|
| `--source / -s`         | URL or path to ingest                               |
| `--version / -v`        | Git tag to check out (git sources only)             |
| `--docs-path / -d`      | Subdirectory to include (repeatable)                |
| `--filter-keyword / -f` | Filter sitemap URLs by keyword (repeatable)         |
| `--yes / -y`            | Skip confirmation prompt                            |
| `--sources-file`        | Custom sources.json path                            |
| `--trim-query-params`   | Strip query parameters from sitemap URLs            |

### Extraction-only commands

```bash
# Extract from sitemap to raw_data (no embedding)
openground extract-sitemap --sitemap-url URL --library NAME

# Extract from git repo to raw_data (no embedding)
openground extract-git --repo-url URL --library NAME --docs-path docs/

# Embed previously extracted raw_data
openground embed LIBRARY --version VERSION
```

### Database commands

```bash
openground list-libraries          # list indexed libraries
openground list-raw-libraries      # list extracted-but-not-embedded data
openground remove LIBRARY --version VERSION   # remove from LanceDB
openground nuke all                # delete all data (raw + embeddings)
openground nuke raw_data           # delete only raw extracted files
openground nuke embeddings         # delete only the LanceDB database
```

### Stats

```bash
openground stats show    # MCP tool call counts + chunk/library counts
openground stats reset   # reset call counts
```

---

## Configuration

Config file: `~/.config/openground/config.json`

```bash
openground config show             # current config
openground config show --defaults  # factory defaults
openground config get KEY          # single value (dot notation)
openground config set KEY VALUE    # set value
openground config reset            # delete config file, restore defaults
```

### All options

| Key                              | Default                                    |
|----------------------------------|--------------------------------------------|
| `db_path`                        | `~/.local/share/openground/lancedb`        |
| `table_name`                     | `documents`                                |
| `raw_data_dir`                   | `~/.local/share/openground/raw_data`       |
| `embeddings.embedding_model`     | `BAAI/bge-small-en-v1.5`                   |
| `embeddings.embedding_backend`   | `fastembed`                                |
| `embeddings.embedding_dimensions`| `384`                                      |
| `embeddings.chunk_size`          | `800`                                      |
| `embeddings.chunk_overlap`       | `200`                                      |
| `embeddings.batch_size`          | `32`                                       |
| `extraction.concurrency_limit`   | `50`                                       |
| `query.top_k`                    | `5`                                        |
| `sources.auto_add_local`         | `true`                                     |

`embedding_backend` must be `"fastembed"` or `"sentence-transformers"`.

> **Note:** changing `embedding_model` or `embedding_backend` after you have
> indexed data will cause an error on the next ingest, because the stored
> vectors would be incompatible. Either revert the config or run
> `openground nuke embeddings` to start fresh.

---

## Data Storage

All data lives under two XDG directories (overridable via `XDG_DATA_HOME`
and `XDG_CONFIG_HOME`):

```
~/.config/openground/
  config.json                   ← configuration

~/.local/share/openground/
  lancedb/                      ← vector database (LanceDB)
  raw_data/
    {library}/
      {version}/
        {page}.json             ← one JSON file per extracted page
  stats.json                    ← MCP tool call counters

~/.openground/
  sources.json                  ← user-wide source registry
```

Typical disk usage: ~100–500 MB per 1 000 pages depending on content size.

---

## MCP Tools

The MCP server (`openground-mcp`) exposes three tools to AI agents:

### `list_libraries_tool`

Returns all indexed libraries and their available versions.

```
{}  →  {"fastapi": ["latest", "v0.100.0"], "numpy": ["latest"]}
```

### `search_documents_tool`

Hybrid semantic + BM25 search over a library's documentation.

```
{
  "query": "how to define a route",
  "library_name": "fastapi",
  "version": "latest"
}
→  top-k results as markdown snippets with source URLs
```

### `get_full_content_tool`

Retrieve the full text of a specific page by URL (useful when a search
snippet isn't enough context).

```
{"url": "https://...", "version": "latest"}
→  full page content as markdown
```

The server pre-loads the embedding model and warms the metadata cache in
a background thread at startup, so the first query is fast.

---

---

## Development

```bash
git clone https://github.com/poweroutlet2/openground.git
cd openground
uv sync .
```

---

## License

MIT
