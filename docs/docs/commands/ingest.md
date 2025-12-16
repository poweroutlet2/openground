# ingest

Process extracted documentation, generate embeddings, and load into LanceDB for searching.

## Usage

```bash
openground ingest --library example-docs
```

## Description

The `ingest` command takes JSON files from the raw data directory and:

1. Loads all JSON documents for the specified library
2. Splits documents into chunks with configurable size and overlap
3. Generates embeddings for each chunk using a local sentence-transformer model
4. Stores vectors and creates a BM25 full-text search index in LanceDB

This enables hybrid search combining semantic similarity and keyword matching.

## Arguments

### Required

#### `--library`, `-l`

The name of the library to ingest from `raw_data/{library}`.

```bash
openground ingest --library databricks
```

This library must have been previously extracted using the [`extract`](extract.md) command.

### Optional

#### `--batch-size`, `-bs`

Batch size for embedding generation (default: 32, or from config).

```bash
openground ingest --library NAME --batch-size 16
```

- **Larger batches** (64, 128): Faster ingestion, more memory usage
- **Smaller batches** (8, 16): Slower ingestion, less memory usage

Use smaller batches on resource-constrained machines.

#### `--chunk-size`, `-cs`

Maximum characters per document chunk (default: 1000, or from config).

```bash
openground ingest --library NAME --chunk-size 1500
```

- **Smaller chunks** (500-800): More precise search results, less context per result
- **Larger chunks** (1500-2000): More context per result, potentially less precise

#### `--chunk-overlap`, `-co`

Overlap size between consecutive chunks (default: 200, or from config).

```bash
openground ingest --library NAME --chunk-overlap 300
```

Overlap ensures context isn't lost at chunk boundaries. Should be about 20% of chunk size.

## Examples

### Basic Ingestion

```bash
openground ingest --library python-docs
```

Uses defaults from your config file.

### Custom Chunking

For more precise search with smaller chunks:

```bash
openground ingest \
  --library example-docs \
  --chunk-size 800 \
  --chunk-overlap 150
```

For more context per result:

```bash
openground ingest \
  --library example-docs \
  --chunk-size 2000 \
  --chunk-overlap 400
```

### Memory-Constrained Environment

```bash
openground ingest \
  --library example-docs \
  --batch-size 8 \
  --chunk-size 600
```

## Data Flow

```
raw_data/{library}/*.json
    ↓
Load JSON files
    ↓
Split into chunks (chunk_size, chunk_overlap)
    ↓
Generate embeddings (batch_size)
    ↓
Store in LanceDB (db_path/table_name)
    ↓
Ready for querying
```

## Embedding Model

By default, openground uses `sentence-transformers/all-MiniLM-L6-v2`:

- **Size**: ~80MB
- **Dimensions**: 384
- **Quality**: Good for most use cases
- **Speed**: Fast on CPU

The model downloads automatically on first use and is cached locally.

### Changing the Embedding Model

To use a different model, update your config (requires re-ingestion):

```bash
# Better quality, larger model
openground config set embedding_model sentence-transformers/all-mpnet-base-v2
openground config set embedding_dimensions 768

# Then re-ingest
openground ingest --library NAME
```

See [Configuration](../configuration.md#embedding-model-settings) for more details.

## Re-ingesting

If you change chunking parameters or embedding models, you can re-ingest without re-extracting:

```bash
# Update config
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300

# Re-ingest (keeps existing vectors, adds new ones)
openground ingest --library NAME
```

!!! note
    Re-ingesting adds new vectors alongside old ones. To completely replace, remove the library first:
    ```bash
    openground rm NAME -y
    openground ingest --library NAME
    ```

## Performance

Ingestion speed depends on:

- **Document size**: Larger documents take longer to chunk and embed
- **Batch size**: Larger batches are faster but use more memory
- **Hardware**: GPU acceleration not currently supported
- **First run**: Downloads the embedding model (~80MB)

Typical performance on a modern laptop:

- ~100-500 chunks per second
- ~1000 pages in 5-10 minutes

## Configuration

Set default ingestion parameters:

```bash
openground config set ingestion.batch_size 32
openground config set ingestion.chunk_size 1000
openground config set ingestion.chunk_overlap 200
```

CLI flags override config values. See [Configuration](../configuration.md) for more details.

## Output

Data is stored in LanceDB at:

```
{db_path}/{table_name}/
```

Default: `~/.local/share/openground/lancedb/documents/`

The database contains:

- **Vector embeddings**: For semantic search
- **Full text content**: For BM25 keyword search
- **Metadata**: URL, library name, chunk index

## Next Steps

After ingestion:

1. **Query your docs**: [`openground query "search" --library NAME`](query.md)
2. **List libraries**: [`openground ls`](list-libraries.md)
3. **Setup MCP**: [MCP Integration](../mcp-integration.md) for AI agents

## Troubleshooting

### Out of Memory

Reduce batch size:

```bash
openground ingest --library NAME --batch-size 8
```

### Slow Ingestion

Increase batch size (if you have enough memory):

```bash
openground ingest --library NAME --batch-size 64
```

### Model Download Fails

The embedding model downloads from HuggingFace on first use. If it fails:

- Check your internet connection
- Try again (downloads are resumed if interrupted)
- Manually download and cache the model

### No JSON Files Found

Make sure you've extracted the library first:

```bash
openground extract --sitemap-url URL --library NAME
```

The raw data should be in `~/.local/share/openground/raw_data/NAME/`.

## See Also

- [extract](extract.md) - Extract documentation first
- [query](query.md) - Search ingested documentation
- [Configuration](../configuration.md) - Customize ingestion settings

