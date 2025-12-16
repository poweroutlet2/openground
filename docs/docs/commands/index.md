# Commands Overview

Openground provides a comprehensive CLI for managing documentation libraries. This section covers all available commands.

## Core Workflow Commands

### [extract](extract.md)
Fetch and parse documentation pages from a sitemap URL.

```bash
openground extract --sitemap-url URL --library NAME
```

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

## Combined Commands

### extract-and-ingest
Extract and ingest in one step (combines `extract` and `ingest`).

```bash
openground extract-and-ingest \
  --sitemap-url URL \
  --library NAME \
  -y
```

All flags from both `extract` and `ingest` are available.

### install-mcp
Configure the MCP server for AI coding assistants.

```bash
openground install-mcp              # Show config
openground install-mcp --cursor     # Auto-configure Cursor
openground install-mcp --claude-code # Auto-configure Claude Code
openground install-mcp --opencode   # Auto-configure OpenCode
```

See [MCP Integration](../mcp-integration.md) for details.

## Command Reference Quick Guide

| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `extract` | Download docs from sitemap | `--sitemap-url`, `--library`, `-f` (filter) |
| `ingest` | Index docs in database | `--library`, `--chunk-size`, `--batch-size` |
| `query` | Search documentation | query text, `--library`, `--top-k` |
| `ls` | List libraries | None |
| `rm` | Remove library | library name, `-y` (skip confirm) |
| `config` | Manage settings | `show`, `get`, `set`, `reset`, `path` |
| `extract-and-ingest` | Extract + ingest | All extract and ingest flags |
| `install-mcp` | Setup MCP server | `--cursor`, `--claude-code`, `--opencode` |

## Common Patterns

### Process New Documentation

```bash
# Extract, ingest, and verify
openground extract-and-ingest -s URL -l NAME -y
openground ls
openground query "test query" -l NAME
```

### Update Existing Documentation

```bash
# Remove old, extract new
openground rm OLD_NAME -y
openground extract-and-ingest -s URL -l NEW_NAME -y
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

- [extract](extract.md) - Detailed extraction options
- [ingest](ingest.md) - Chunking and embedding configuration
- [query](query.md) - Search and filtering
- [ls](list-libraries.md) - Listing libraries
- [rm](remove-library.md) - Removing libraries
- [config](config.md) - Configuration management

