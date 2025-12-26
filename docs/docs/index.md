# Openground

Openground is a system for managing documentation in an agent-friendly manner. It has a CLI to extract and store docs from websites and exposes tools via MCP to AI coding agents for querying the data via hybrid BM25 full-text search and vector similarity search.

## Why Openground?

Modern AI coding assistants need access to up-to-date documentation to provide accurate help. Openground bridges this gap by:

- **Extracting** documentation from websites via sitemaps or git repositories
- **Indexing** content with hybrid search (semantic + BM25)
- **Serving** documentation to AI agents through the Model Context Protocol (MCP)

Your AI assistant can then query your project's documentation directly, getting accurate, context-aware answers.

## Architecture

```
          ┌─────────────────────────────────────────────────────────────────────────────┐
          │                              OPENGROUND                                     │
          ├─────────────────────────────────────────────────────────────────────────────┤
          │                                                                             │
          │  ┌───────────────────────────────────────────────────────────────────────┐  │
          │  │                           INGESTION PIPELINE                          │  │
          │  │                                                                       │  │
          │  │                                                                       |  |  
          │  │   ┌─────────────┐     ┌─────────────┐     ┌─────────────────────┐     │  │
          │  │   │   EXTRACT   │     │    EMBED    │     │    LOCAL LANCEDB    │     │  │
          │  │   │  • Sitemap  │     │  • Chunking │     │  • Vector Store     │     │  │
          │  │   │    Parsing  │────>│  • Local    │────>│  • BM25 FTS Index   │     │  │
          │  │   │  • Git Repo │     │    Embedding│     │  • Hybrid Search    │     │  │
          │  │   │    Walking  │     │    Model    │     │                     │     │  │
          │  │   └─────────────┘     └─────────────┘     └──────────┬──────────┘     │  │
          │  │         │                    ^                       │                │  │
          │  │         ▼                    |                       │                │  │
          │  │   ┌─────────────┐            |                       │                │  │
          │  │   │     JSON    │ ───────────┘                       │                │  │
          │  │   │  (raw_data/)│                                    │                │  │
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
          │  │   │  openground rm      │      │  • search_available_libs_tool   │    │  │
          │  │   │  openground config  │      │  • get_full_content_tool        │    │  │
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

## Data Flow

### 1. Extract (`openground add`, `extract`, or `extract-git`)
- Parses sitemap XML from documentation websites OR walks files in a git repository
- Downloads and scrapes page content (for sitemaps) or reads markdown/text files (for git)
- Saves content in structured JSON format into the raw data directory
- Uses aiohttp and trafilatura for web scraping, or shallow git clones for repositories

### 2. Embed (`openground embed`)
- Loads JSON files from the raw data directory
- Splits documents into chunks with configurable overlap
- Generates embeddings using a local model (sentence-transformers)
- Stores vectors and creates BM25 full-text search index in LanceDB
- Uses langchain-text-splitters and sentence-transformers

### 3. Query (CLI or MCP)
- Performs hybrid search combining semantic similarity and BM25 ranking
- Returns ranked results with source URLs and relevance scores
- Full page content can be retrieved for deeper context

## Quick Example

```bash
# Install openground (recommended)
uv tool install openground

# Or using pip
pip install openground

# Extract and embed documentation from a sitemap
openground add example-docs \
  --source https://docs.example.com/sitemap.xml \
  -y

# Or from a git repository
openground add example-docs \
  --source https://github.com/example/repo.git \
  -y

# Query from CLI
openground query "how to authenticate" --library example-docs

# Or use with AI agents via MCP
openground install-mcp --cursor
```

## Next Steps

- [Getting Started](getting-started.md) - Install and configure openground
- [Configuration](configuration.md) - Customize settings for your needs
- [Commands](commands/index.md) - Detailed command reference
- [MCP Integration](mcp-integration.md) - Connect to AI coding assistants
