# Configuration

Openground uses a JSON configuration file to store persistent settings. This page covers how to manage your configuration and what options are available.

## Configuration File Location

The config file is stored in a platform-appropriate location:

- **Linux/macOS**: `~/.config/openground/config.json`
- **Windows**: `~/AppData/Local/openground/config.json`

You can override this by setting the `XDG_CONFIG_HOME` environment variable.

## Default Configuration

Openground uses sensible defaults that work for most use cases. The configuration file is created automatically on first use with these defaults.

View your current effective configuration:

```bash
openground config show
```

## Managing Configuration

### View Config File Location

```bash
openground config path
```

### Get a Specific Value

```bash
openground config get db_path
openground config get ingestion.chunk_size
```

Use dot notation to access nested values.

### Set Configuration Values

```bash
openground config set db_path ~/custom/path/to/lancedb
openground config set ingestion.chunk_size 1500
openground config set query.top_k 10
```

### Reset to Defaults

Delete the configuration file and restore all defaults:

```bash
openground config reset
```

!!! warning
    This deletes your config file. The database and data files are not affected.

## Configuration Schema

### Full Schema Reference

```json
{
  "db_path": "~/.local/share/openground/lancedb",
  "table_name": "documents",
  "extraction": {
    "concurrency_limit": 50
  },
  "ingestion": {
    "batch_size": 32,
    "chunk_size": 1000,
    "chunk_overlap": 200
  },
  "query": {
    "top_k": 5
  },
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_dimensions": 384
}
```

### Configuration Options

#### Database Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `db_path` | string | `~/.local/share/openground/lancedb` | Path to LanceDB database directory |
| `table_name` | string | `documents` | Name of the database table |

!!! note
    The `db_path` uses platform-specific defaults:
    
    - Linux/macOS: `~/.local/share/openground/lancedb`
    - Windows: `~/AppData/Local/openground/lancedb`

#### Extraction Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `extraction.concurrency_limit` | integer | `50` | Maximum concurrent HTTP requests during extraction |

Lower this value if you're experiencing timeouts or rate limiting:

```bash
openground config set extraction.concurrency_limit 10
```

#### Ingestion Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ingestion.batch_size` | integer | `32` | Batch size for generating embeddings |
| `ingestion.chunk_size` | integer | `1000` | Maximum characters per document chunk |
| `ingestion.chunk_overlap` | integer | `200` | Overlap between consecutive chunks |

**Chunk Size**: Controls how documents are split. Smaller chunks = more precise search, larger chunks = more context per result.

**Chunk Overlap**: Ensures context isn't lost at chunk boundaries. A 200-character overlap means the last 200 chars of one chunk overlap with the first 200 chars of the next.

**Batch Size**: Affects memory usage during ingestion. Lower values use less memory but take longer.

Example adjustments:

```bash
# More granular chunks for precise searches
openground config set ingestion.chunk_size 500
openground config set ingestion.chunk_overlap 100

# Larger chunks for more context
openground config set ingestion.chunk_size 2000
openground config set ingestion.chunk_overlap 400
```

#### Query Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `query.top_k` | integer | `5` | Number of results to return by default |

```bash
openground config set query.top_k 10
```

#### Embedding Model Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `embedding_model` | string | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model identifier |
| `embedding_dimensions` | integer | `384` | Embedding vector dimensions |

!!! warning "Changing Embedding Models"
    If you change the embedding model or dimensions, you must re-ingest all your libraries. The model downloads on first use and is cached locally.

Popular alternative models:

```bash
# Faster, smaller model (good for resource-constrained environments)
openground config set embedding_model sentence-transformers/all-MiniLM-L12-v2
openground config set embedding_dimensions 384

# Better quality, larger model
openground config set embedding_model sentence-transformers/all-mpnet-base-v2
openground config set embedding_dimensions 768
```

## Configuration Precedence

For options that support CLI flags, the precedence order is:

1. **CLI flag** (highest priority)
2. **Config file value**
3. **Hardcoded default** (lowest priority)

### Example

If your config has:

```json
{
  "query": {
    "top_k": 10
  }
}
```

Running `openground query "test" --top-k 3` will return **3 results** (CLI flag wins).

Running `openground query "test"` will return **10 results** (config value).

### Config-Only Options

These options can **only** be set via `openground config set` and have no CLI flags:

- `db_path`
- `table_name`
- `embedding_model`
- `embedding_dimensions`

This ensures consistency across all commands accessing the database.

## Data Storage

In addition to the configuration file, openground stores data in:

- **Raw extracted data**: `~/.local/share/openground/raw_data/{library}/`
- **Database**: Path specified by `db_path` (default: `~/.local/share/openground/lancedb/`)

On Windows, the data directory is `~/AppData/Local/openground/`.

You can override the data directory by setting the `XDG_DATA_HOME` environment variable.

## Examples

### Development Setup

For development, you might want faster extraction and smaller chunks:

```bash
openground config set extraction.concurrency_limit 20
openground config set ingestion.chunk_size 800
openground config set ingestion.batch_size 16
```

### Production Setup

For production with better quality search:

```bash
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300
openground config set query.top_k 10
openground config set embedding_model sentence-transformers/all-mpnet-base-v2
openground config set embedding_dimensions 768
```

### Resource-Constrained Environment

If running on a machine with limited memory:

```bash
openground config set extraction.concurrency_limit 10
openground config set ingestion.batch_size 8
openground config set ingestion.chunk_size 600
```

