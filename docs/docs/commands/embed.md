# embed

Process extracted documentation, generate embeddings, and load into LanceDB for searching.

## Usage

```bash
openground embed example-docs
```

## Description

The `embed` command takes JSON files from the raw data directory and:

1. Loads all JSON documents for the specified library
2. Splits documents into chunks with configurable size and overlap
3. Generates embeddings for each chunk using a local sentence-transformer model
4. Stores vectors and creates a BM25 full-text search index in LanceDB

This enables hybrid search combining semantic similarity and keyword matching.

## Arguments

### Required

#### `library` (Positional)

The name of the library to embed from `raw_data/{library}`.

```bash
openground embed databricks
```

This library must have been previously extracted using the [`extract`](extract.md) command.

## Examples

### Basic Embedding

```bash
openground embed python-docs
```

Uses defaults from your config file.

### Custom Chunking

To customize chunking parameters, set them in your config file before running embed:

```bash
# Set chunking parameters
openground config set ingestion.chunk_size 800
openground config set ingestion.chunk_overlap 150

# Then embed
openground embed example-docs
```

For more context per result:

```bash
openground config set ingestion.chunk_size 2000
openground config set ingestion.chunk_overlap 400
openground embed example-docs
```

### Memory-Constrained Environment

```bash
openground config set ingestion.batch_size 8
openground config set ingestion.chunk_size 600
openground embed example-docs
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

-   **Size**: ~80MB
-   **Dimensions**: 384
-   **Quality**: Good for most use cases
-   **Speed**: Fast on CPU

The model downloads automatically on first use and is cached locally.

### Changing the Embedding Model

To use a different model, update your config (requires re-embedding):

```bash
# Better quality, larger model
openground config set embedding_model sentence-transformers/all-mpnet-base-v2
openground config set embedding_dimensions 768

# Then re-embed
openground embed NAME
```

See [Configuration](../configuration.md#embedding-model-settings) for more details.

## Re-embedding

If you change chunking parameters or embedding models, you can re-embed without re-extracting:

```bash
# Update config
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300

# Re-embed (keeps existing vectors, adds new ones)
openground embed NAME
```

!!! note
Re-embedding adds new vectors alongside old ones. To completely replace, remove the library first:
`bash
    openground rm NAME -y
    openground embed NAME
    `

## Performance

Embedding speed depends on:

-   **Document size**: Larger documents take longer to chunk and embed
-   **Batch size**: Larger batches are faster but use more memory
-   **Hardware**: GPU acceleration not currently supported
-   **First run**: Downloads the embedding model (~80MB)

Typical performance on a modern laptop:

-   ~100-500 chunks per second
-   ~1000 pages in 5-10 minutes

## Configuration

Set default embedding parameters:

```bash
openground config set ingestion.batch_size 32
openground config set ingestion.chunk_size 1000
openground config set ingestion.chunk_overlap 200
```

These values are used when you run `openground embed`. See [Configuration](../configuration.md) for more details.

## Output

Data is stored in LanceDB at:

```
{db_path}/{table_name}/
```

Default: `~/.local/share/openground/lancedb/documents/`

The database contains:

-   **Vector embeddings**: For semantic search
-   **Full text content**: For BM25 keyword search
-   **Metadata**: URL, library name, chunk index

## Next Steps

After embedding:

1. **Query your docs**: [`openground query "search" --library NAME`](query.md)
2. **List libraries**: [`openground ls`](list-libraries.md)
3. **Setup MCP**: [MCP Integration](../mcp-integration.md) for AI agents

## Troubleshooting

### Out of Memory

Reduce batch size in your config:

```bash
openground config set ingestion.batch_size 8
openground embed NAME
```

### Slow Embedding

Increase batch size in your config (if you have enough memory):

```bash
openground config set ingestion.batch_size 64
openground embed NAME
```

### Model Download Fails

The embedding model downloads from HuggingFace on first use. If it fails:

-   Check your internet connection
-   Try again (downloads are resumed if interrupted)
-   Manually download and cache the model

### No JSON Files Found

Make sure you've extracted the library first:

```bash
openground extract --sitemap-url URL --library NAME
```

The raw data should be in `~/.local/share/openground/raw_data/NAME/`.

## See Also

-   [extract](extract.md) - Extract documentation first
-   [query](query.md) - Search embedded documentation
-   [Configuration](../configuration.md) - Customize embedding settings
