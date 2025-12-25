# Commands Overview

Openground provides a comprehensive CLI for managing documentation libraries. This section covers all available commands.

## Core Workflow Commands

### [add](add.md)
Extract and ingest documentation in one step. Automatically detects if the source is a sitemap or a git repository.

```bash
# Using a sitemap
openground add example --source https://docs.example.com/sitemap.xml

# Using a git repo
openground add example --source https://github.com/user/repo.git
```

## Core Extraction Commands

### [extract](extract.md)
Fetch and parse documentation pages from a sitemap URL.

```bash
openground extract --sitemap-url URL --library NAME
```

### [extract-git](extract-git.md)
Extract documentation from a git repository using shallow clone and sparse checkout.

```bash
openground extract-git --repo-url URL --docs-path docs/ --library NAME
```

## Core Processing Commands

### [ingest](ingest.md)
Chunk documents, generate embeddings, and load into LanceDB.

```bash
openground ingest --library NAME
```

### [query](query.md)
Search documentation using hybrid BM25 + semantic search.

```bash
openground query "search terms" --library NAME
```

## Management Commands

### [ls](list-libraries.md)
List all ingested documentation libraries.

```bash
openground ls
```

### [list-raw-libraries](list-libraries.md#list-raw-libraries)
List available libraries in the raw data directory that have been extracted but not yet ingested.

```bash
openground list-raw-libraries
```

### [rm](remove-library.md)
Remove a library from the database.

```bash
openground rm LIBRARY_NAME
```

### [config](config.md)
View and manage openground configuration.

```bash
openground config show
openground config set KEY VALUE
openground config get KEY
```

### [nuke](nuke.md)
Delete all data from raw_data and/or LanceDB directories.

```bash
openground nuke all              # Delete everything
openground nuke raw_data         # Delete only raw data
openground nuke embeddings       # Delete only embeddings
```

## MCP Integration Commands

### install-mcp
Configure the MCP server for AI coding assistants.

```bash
openground install-mcp              # Show config
openground install-mcp --cursor     # Auto-configure Cursor
openground install-mcp --claude-code # Auto-configure Claude Code
openground install-mcp --opencode   # Auto-configure OpenCode
openground install-mcp --wsl        # Generate WSL-compatible config
```

See [MCP Integration](../mcp-integration.md) for details.

## Command Reference Quick Guide

| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `add` | Extract + ingest (auto-detect) | `--source`, `--library`, `--yes` |
| `extract` | Download docs from sitemap | `--sitemap-url`, `--library`, `-f` (filter) |
| `extract-git` | Download docs from git | `--repo-url`, `--docs-path`, `--library` |
| `ingest` | Index docs in database | `--library`, `--chunk-size`, `--batch-size` |
| `query` | Search documentation | query text, `--library`, `--top-k` |
| `ls` | List ingested libraries | None |
| `list-raw-libraries` | List raw data libraries | None |
| `rm` | Remove library | library name, `-y` (skip confirm) |
| `config` | Manage settings | `show`, `get`, `set`, `reset`, `path` |
| `nuke` | Delete all data | `all`, `raw_data`, `embeddings`, `-y` (skip confirm) |
| `install-mcp` | Setup MCP server | `--cursor`, `--claude-code`, `--opencode`, `--wsl` |

## Common Patterns

### Process New Documentation

```bash
# Extract, ingest, and verify
openground add -s https://docs.example.com/sitemap.xml -l example -y
openground ls
openground query "how to use" -l example
```

### Process from Git

```bash
# Extract from git and ingest
openground add -s https://github.com/example/repo.git -l example -y
```

### Update Existing Documentation

```bash
# Remove old, extract new
openground rm OLD_NAME -y
openground add -s URL -l NEW_NAME -y
```

### Change Chunking Strategy

```bash
# Update config and re-ingest
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300
openground ingest --library NAME
```

## Getting Help

Every command supports `--help`:

```bash
openground --help
openground extract --help
openground config --help
```

## Next Steps

Browse the detailed documentation for each command:

- [add](add.md) - Extract and ingest in one step
- [extract](extract.md) - Detailed extraction options
- [extract-git](extract-git.md) - Extract from git repositories
- [ingest](ingest.md) - Chunking and embedding configuration
- [query](query.md) - Search and filtering
- [ls](list-libraries.md) - Listing libraries
- [rm](remove-library.md) - Removing libraries
- [config](config.md) - Configuration management
- [nuke](nuke.md) - Deleting all data
