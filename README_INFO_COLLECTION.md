# OpenGround - README Information Collection

This document contains all the information collected about the OpenGround project for creating a comprehensive README.

## Project Overview

**Name:** OpenGround  
**Version:** 0.1.0  
**Python Required:** >= 3.10  
**Current Testing Environment:** Python 3.12.12  
**Package Manager:** uv (modern Python package manager)  
**Total Source Code:** ~800 lines across 7 Python files

### Purpose
OpenGround is a tool that enables managing a local vector database of documentation for coding libraries and frameworks and exposes it to AI agents via the Model Context Protocol (MCP).

### Future Vision
The goal is to provide a hosted service that:
- Manages the pipeline of ingesting documentation
- Hosts the documentation database
- Manages automatic updates of documentation
- Exposes the MCP server to clients

## Architecture & Components

### Core Components

1. **CLI Tool (`openground` command)**
   - Unified interface for extraction, ingestion, and querying
   - Built with Typer framework
   - 4 main commands: extract, ingest, query, list-libraries

2. **MCP Server (`src/server.py`)**
   - Built on FastMCP (>= 2.13.3)
   - Runs on stdio transport
   - Exposes 3 tools for AI agents:
     - `search_documents`: Hybrid search (semantic + BM25)
     - `list_collections`: List available documentation collections
     - `get_full_content`: Retrieve full document content by URL

3. **Document Extraction (`src/extract.py`)**
   - Fetches documentation from sitemaps
   - Uses trafilatura for HTML parsing and conversion to markdown
   - Async/concurrent processing with configurable limits
   - Progress tracking with tqdm

4. **Document Ingestion (`src/ingest.py`)**
   - Chunks documents using LangChain's RecursiveCharacterTextSplitter
   - Generates embeddings using sentence-transformers
   - Stores in LanceDB with vector indices
   - Creates full-text search (BM25) indices
   - Hardware acceleration support (CUDA, MPS, CPU)

5. **Search/Query (`src/query.py`)**
   - Hybrid search combining:
     - Semantic search (vector similarity)
     - BM25 (full-text search)
   - Filterable by collection/library
   - Returns markdown-formatted results with tool hints

## Technical Stack

### Dependencies

**Core Libraries:**
- `lancedb` + `lance` (>= 1.2.1) - Vector database
- `sentence-transformers` - Embedding generation
- `torch` - ML framework (backend for embeddings)
- `trafilatura` - Web scraping and HTML extraction
- `aiohttp` - Async HTTP client
- `typer` - CLI framework
- `fastmcp` (>= 2.13.3) - MCP server framework
- `langchain-text-splitters` - Document chunking
- `pandas` (>= 2.3.3) - Data manipulation
- `pydantic` - Data validation
- `tqdm` - Progress bars

**Dev Dependencies:**
- `ruff` (>= 0.14.8) - Linter/formatter
- `jupyter` - Notebook support
- `ipynb` - Notebook utilities

### Data Storage

**Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2`
- 384-dimensional vectors
- Normalized embeddings
- Device-agnostic (CUDA/MPS/CPU)

**Vector Database:** LanceDB
- Default path: `lancedb_data/`
- Default table: `documents`
- Schema includes: url, collection_title, title, description, last_modified, content, chunk_index, vector

**Raw Data Storage:**
- Default path: `raw_data/docs/{collection_title}/`
- Format: JSON files (one per document)
- Example data: 3,617 Databricks documentation pages (~33MB)
- Database size: ~174MB (with embeddings and indices)

## Features & Capabilities

### 1. Documentation Extraction

**Command:** `openground extract`

**Features:**
- Sitemap-based crawling
- Concurrent fetching (configurable limit, default: 50)
- URL filtering by keywords
- HTML → Markdown conversion
- Metadata extraction (title, description, last_modified)
- Progress tracking
- Error handling and retry logic

**Output:** JSON files with structured data:
```json
{
  "url": "https://...",
  "collection_title": "Library Name",
  "title": "Page Title",
  "description": "Page description",
  "last_modified": "Thu, 11 Dec 2025 00:22:47 GMT",
  "content": "# Markdown content..."
}
```

**Configuration Options:**
- `--sitemap-url` / `-s`: Root sitemap URL
- `--concurrency-limit` / `-c`: Max concurrent requests (default: 50)
- `--collection-title` / `-t`: Label for docs collection (default: "Databricks")
- `--output-dir` / `-o`: Output directory (default: `raw_data/docs/{collection_title}`)
- `--filter-keyword` / `-f`: URL filter keywords (repeatable, default: ["docs", "documentation", "blog"])

**Example:**
```bash
openground extract \
  --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
  --concurrency-limit 50 \
  --collection-title Databricks \
  --output-dir raw_data/docs/Databricks \
  -f docs -f documentation -f blog
```

### 2. Document Ingestion

**Command:** `openground ingest`

**Features:**
- Document chunking with overlap
- Batch embedding generation
- Vector index creation
- Full-text search (BM25) index creation
- Progress tracking for all stages
- Hardware acceleration (CUDA/MPS/CPU auto-detection)

**Configuration Options:**
- `--data-dir` / `-d`: Directory with extracted JSON files
- `--db-path` / `-b`: LanceDB storage directory (default: `lancedb_data`)
- `--table-name` / `-t`: Table name (default: `documents`)
- `--chunk-size` / `-cs`: Chunk size for splitting (default: 1000)
- `--chunk-overlap` / `-co`: Overlap between chunks (default: 200)
- `--batch-size` / `-bs`: Batch size for embeddings (default: 32)

**Example:**
```bash
openground ingest \
  --data-dir raw_data/docs/Databricks \
  --db-path lancedb_data \
  --table-name documents \
  --chunk-size 1000 \
  --chunk-overlap 200 \
  --batch-size 32
```

### 3. Querying / Search

**Command:** `openground query`

**Features:**
- Hybrid search (semantic + BM25)
- Collection filtering
- Configurable result count
- Markdown-formatted output
- Tool hints for full content retrieval

**Configuration Options:**
- Query string (positional argument)
- `--collection-title` / `-c`: Filter by collection
- `--db-path` / `-d`: LanceDB path (default: `lancedb_data`)
- `--table-name` / `-t`: Table name (default: `documents`)
- `--top-k` / `-k`: Number of results (default: 5)

**Example:**
```bash
openground query "how to connect" \
  --db-path lancedb_data \
  --table-name documents \
  --collection-title Databricks \
  --top-k 5
```

### 4. List Libraries

**Command:** `openground list-libraries`

**Features:**
- Lists all unique collection titles in the database
- Sorted alphabetically
- Useful for discovering available documentation

**Configuration Options:**
- `--db-path` / `-d`: LanceDB path
- `--table-name` / `-t`: Table name

**Example:**
```bash
openground list-libraries --db-path lancedb_data --table-name documents
```

### 5. MCP Server

**Run Command:** `python src/server.py` (or via MCP client configuration)

**MCP Tools Exposed:**

1. **search_documents(query: str, collection_title: str) → str**
   - Search documentation with hybrid search
   - Returns top 5 results
   - Includes snippets and source URLs

2. **list_collections() → list[str]**
   - Returns list of available documentation collections
   - Helps agents discover what docs are available

3. **get_full_content(url: str) → str**
   - Retrieves all chunks for a given URL
   - Returns full document content
   - Useful when search snippet isn't enough

**MCP Server Configuration:**
- Name: "Documentation Search"
- Transport: stdio
- Database path: `lancedb_data/` (hardcoded in server.py)
- Table name: `documents` (hardcoded in server.py)

## Installation

### Requirements
- Python >= 3.10
- uv package manager (recommended) or pip

### Installation Steps

1. **Clone the repository** (when available)

2. **Install with uv:**
   ```bash
   uv pip install -e .
   ```

3. **Or install with pip:**
   ```bash
   pip install -e .
   ```

4. **Verify installation:**
   ```bash
   openground --help
   ```

## Usage Workflow

### Basic Workflow: Extract → Ingest → Query

1. **Extract documentation:**
   ```bash
   openground extract \
     --sitemap-url https://docs.example.com/sitemap.xml \
     --collection-title "MyLibrary" \
     --output-dir raw_data/docs/MyLibrary
   ```

2. **Ingest into vector database:**
   ```bash
   openground ingest \
     --data-dir raw_data/docs/MyLibrary \
     --db-path lancedb_data \
     --table-name documents
   ```

3. **Query the documentation:**
   ```bash
   openground query "how to install" \
     --collection-title "MyLibrary" \
     --top-k 5
   ```

4. **List available libraries:**
   ```bash
   openground list-libraries
   ```

### Using the MCP Server

The MCP server allows AI agents (like Claude Desktop) to access the documentation database.

**To run the server:**
```bash
python src/server.py
```

**MCP Client Configuration (Claude Desktop example):**
```json
{
  "mcpServers": {
    "openground": {
      "command": "python",
      "args": ["/path/to/openground/src/server.py"],
      "env": {}
    }
  }
}
```

Note: The server paths for `db_path` and `table_name` are currently hardcoded in `server.py` and may need adjustment based on your setup.

## Project Structure

```
openground/
├── src/
│   ├── __init__.py          # Package marker
│   ├── cli.py               # CLI commands (155 lines)
│   ├── config.py            # Configuration defaults (25 lines)
│   ├── extract.py           # Sitemap extraction & HTML parsing (183 lines)
│   ├── ingest.py            # Chunking & embedding pipeline (217 lines)
│   ├── query.py             # Hybrid search implementation (138 lines)
│   └── server.py            # MCP server with FastMCP (76 lines)
├── raw_data/                # Extracted JSON files (gitignored)
│   └── docs/
│       └── {collection}/
├── lancedb_data/            # Vector database files (gitignored)
│   └── documents.lance/
├── pyproject.toml           # Project metadata & dependencies
├── uv.lock                  # Dependency lock file
├── README.md                # Current minimal README
└── .gitignore               # Git ignore rules
```

## Configuration

### Default Settings (src/config.py)

```python
# Collection settings
DEFAULT_COLLECTION_TITLE = "Databricks"

# Extraction
SITEMAP_URL = "https://docs.databricks.com/aws/en/sitemap.xml"
CONCURRENCY_LIMIT = 50
FILTER_KEYWORDS = ["docs", "documentation", "blog"]

# Storage paths
DEFAULT_DB_PATH = Path("lancedb_data")
DEFAULT_TABLE_NAME = "documents"

# Embedding model
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
```

All defaults can be overridden via CLI flags.

## Performance Characteristics

### Tested Scale (Databricks docs example)
- **Documents extracted:** 3,617 pages
- **Raw data size:** 33 MB
- **Database size:** 174 MB (with vectors and indices)
- **Concurrency:** 50 concurrent requests for extraction
- **Batch size:** 32 documents per embedding batch

### Hardware Acceleration
- Automatically detects and uses:
  - CUDA (NVIDIA GPUs)
  - MPS (Apple Silicon)
  - CPU (fallback)

### Search Performance
- Hybrid search combines vector similarity + BM25
- Full-text index for fast keyword matching
- Vector index for semantic similarity
- Sub-second query response times (typical)

## Known Limitations & Considerations

1. **MCP Server Paths:** Database and table paths are hardcoded in `server.py` (lines 7-8). Need to make configurable or read from environment.

2. **Data Persistence:** Raw data and vector database are gitignored. Need to consider backup/sync strategies.

3. **Update Strategy:** No built-in mechanism for updating documentation. Need to re-run extract + ingest for updates.

4. **Memory Usage:** Embedding generation can be memory-intensive for large batches. Batch size can be adjusted.

5. **No Authentication:** The MCP server has no authentication mechanism. Suitable for local use only.

6. **Single Database:** All collections are stored in the same database/table. Consider separate tables per collection for large deployments.

7. **No Incremental Updates:** Currently requires full re-ingestion to update. Delta updates would be valuable for large doc sets.

## Development Information

### Build System
- **Build backend:** Hatchling
- **Packages:** `src/` directory
- **Entry point:** `openground` command → `src.cli:app`

### Code Quality
- **Linter:** Ruff (>= 0.14.8)
- **Type hints:** Partial (TypedDict used for ParsedPage)
- **Progress tracking:** tqdm for all long-running operations
- **Error handling:** Exception handling in extraction and ingestion

### Development Setup
```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run linter
ruff check src/

# Format code
ruff format src/

# After code changes, reinstall to refresh CLI entrypoint
uv pip install -e .
```

## Use Cases

### Primary Use Case
Enabling AI agents (via MCP) to access and search technical documentation locally, providing:
- Fast, local-first documentation access
- No API rate limits
- Privacy-preserving (no data sent to external services)
- Semantic understanding via embeddings
- Multi-library support

### Additional Use Cases
1. **Personal Documentation Search:** Command-line documentation search across multiple libraries
2. **Team Knowledge Base:** Shared documentation database for development teams
3. **Offline Development:** Access documentation without internet
4. **Custom Documentation:** Ingest internal/proprietary documentation
5. **Documentation Research:** Analyze and compare documentation across libraries

## Future Roadmap (Mentioned Goals)

1. **Hosted Service:** Provide a managed service for:
   - Automated documentation ingestion
   - Scheduled updates
   - Hosted database
   - API/MCP server hosting
   - Multi-tenant support

2. **Documentation Management:**
   - Automatic update detection
   - Version management
   - Change tracking
   - Diff visualization

3. **Enhanced Features:**
   - More embedding models
   - Better chunking strategies
   - Multi-language support
   - Code example extraction
   - API reference parsing

4. **Improved MCP Server:**
   - Configurable paths
   - Authentication
   - Rate limiting
   - Usage analytics

## Key Technical Decisions

1. **LanceDB:** Chosen for vector storage
   - Supports hybrid search (vector + BM25)
   - Apache Arrow-based (fast, memory-efficient)
   - Easy schema management
   - Built-in FTS indexing

2. **Sentence Transformers:** Chosen for embeddings
   - High quality, open-source models
   - Easy to use
   - Hardware acceleration support
   - Small model size (all-MiniLM-L6-v2 is only ~90MB)

3. **Trafilatura:** Chosen for HTML extraction
   - Excellent content extraction quality
   - Markdown output support
   - Metadata extraction
   - Fast and reliable

4. **FastMCP:** Chosen for MCP server
   - Simple, declarative API
   - Type-safe
   - Built-in stdio transport
   - Active development

5. **Typer:** Chosen for CLI
   - Modern Python CLI framework
   - Automatic help generation
   - Type hints → validation
   - Rich terminal output

## Example Output

### Query Output Example
```
Found 5 matches.
1. **Choose where your MLflow data is stored**: "MLflow tracking servers store and manage your experiment data, runs, and models. Configure your tracking servers to control where your MLflow data is stored..." (Source: https://docs.databricks.com/aws/en/mlflow/tracking-server-configuration, score=0.8523)
   To get full page content: {"tool": "get_full_content", "url": "https://docs.databricks.com/aws/en/mlflow/tracking-server-configuration"}
...
```

### List Libraries Output Example
```
AngularJS
Databricks
Django
FastAPI
React
Vue.js
```

## License

**Status:** No license file found in repository (as of collection date)

## Repository Information

**Status:** No git remote configured (local development repository)

## Additional Notes

- Project is in active development (version 0.1.0)
- Code is well-structured and modular
- Good separation of concerns across modules
- Comprehensive progress tracking throughout
- Error handling needs some improvement
- Documentation could be expanded
- Tests not yet implemented

## File Statistics

- Total Python files: 7
- Total lines of code: ~800
- Average file size: ~115 lines
- Largest file: ingest.py (217 lines)
- Smallest file: __init__.py (2 lines)

## Contact & Contribution

**Status:** To be determined (no contributor guidelines or contact info found)

---

**Information Collection Date:** December 13, 2025  
**Collected By:** AI Assistant  
**Purpose:** Preparation for comprehensive README.md creation

