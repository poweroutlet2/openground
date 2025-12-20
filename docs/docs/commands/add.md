# add

Extract documentation pages from a sitemap and ingest them into the database in one step.

## Usage

```bash
openground add \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f docs -f guide \
  -y
```

## Description

The `add` command combines [`extract`](extract.md) and [`ingest`](ingest.md) into a single operation. It:

1. Fetches the sitemap XML from the provided URL
2. Parses all page URLs from the sitemap (including nested sitemaps)
3. Downloads each page concurrently using aiohttp
4. Extracts main content using trafilatura
5. Saves each page as a JSON file in the raw data directory
6. Loads the JSON files and splits them into chunks
7. Generates embeddings using a local sentence-transformer model
8. Stores vectors and creates a BM25 full-text search index in LanceDB

This is the fastest way to get documentation indexed and ready for querying.

!!! tip "When to use `add` vs separate commands"
Use `add` when you want to extract and ingest in one go. Use separate [`extract`](extract.md) and [`ingest`](ingest.md) commands when you want to:

    - Extract once, then re-ingest with different chunking strategies
    - Review extracted content before indexing
    - Keep raw data for backup or analysis
    - Extract from multiple sources before ingesting together

## Arguments

### Required

#### `--sitemap-url`, `-s`

The URL of the sitemap XML file to extract from.

```bash
openground add -s https://docs.databricks.com/aws/en/sitemap.xml -l databricks -y
```

Most documentation sites have a sitemap at `/sitemap.xml`, but some use different paths. Check the site's `robots.txt` file to find the sitemap URL.

#### `--library`, `-l`

The name of the library/framework. This determines where the extracted files are saved and how the library is identified in the database.

```bash
openground add -s URL -l my-project -y
```

Files are saved to `~/.local/share/openground/raw_data/my-project/` and indexed under the name `my-project`.

### Optional

#### `--filter-keyword`, `-f`

Filter URLs to only extract pages containing specific keywords. Can be specified multiple times.

```bash
# Only extract URLs containing "docs" OR "documentation"
openground add -s URL -l NAME -f docs -f documentation -y
```

This is useful for:

-   Excluding blog posts or marketing pages
-   Focusing on specific documentation sections
-   Reducing extraction time and storage

!!! tip
Start without filters to see what URLs are available, then re-run with filters if needed.

#### `--yes`, `-y`

Skip the confirmation prompt between extraction and ingestion.

```bash
openground add -s URL -l NAME -y
```

Without `-y`, you'll be prompted to continue after extraction:

```
✅ Extraction complete: 1,247 pages extracted to /path/to/raw_data/NAME

Press Enter to continue with ingestion, or Ctrl+C to exit...
```

Use `-y` for automated scripts or when you're certain you want to proceed.

## Ingestion Parameters

The `add` command uses configuration values for ingestion parameters. These can be set in your config file:

```bash
# Set chunking parameters
openground config set ingestion.chunk_size 1000
openground config set ingestion.chunk_overlap 200
openground config set ingestion.batch_size 32

# Set embedding model
openground config set ingestion.embedding_model sentence-transformers/all-MiniLM-L6-v2
openground config set ingestion.embedding_dimensions 384
```

See [Configuration](../configuration.md) for all available settings.

!!! note
Unlike the separate `ingest` command, `add` does not support CLI flags for chunking parameters. If you need custom chunking, either:

    1. Set values in your config file before running `add`
    2. Use separate `extract` and `ingest` commands with CLI flags

## Examples

### Basic Usage

Extract and ingest documentation in one command:

```bash
openground add \
  --sitemap-url https://docs.python.org/3/sitemap.xml \
  --library python-docs \
  -y
```

### Filtered Extraction

Extract only tutorial and guide pages:

```bash
openground add \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f tutorial -f guide -f getting-started \
  -y
```

### Interactive Mode

Review extraction results before ingesting:

```bash
openground add \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f docs
```

You'll see:

```
✅ Extraction complete: 1,247 pages extracted to /path/to/raw_data/example-docs

Press Enter to continue with ingestion, or Ctrl+C to exit...
```

Press Enter to proceed with ingestion, or Ctrl+C to cancel.

### With Custom Configuration

Set ingestion parameters before running:

```bash
# Configure chunking
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300

# Extract and ingest with new settings
openground add -s URL -l NAME -y
```

## Data Flow

```
Sitemap URL
    ↓
Extract pages (concurrent downloads)
    ↓
Save JSON files to raw_data/{library}/
    ↓
Load JSON files
    ↓
Split into chunks (from config)
    ↓
Generate embeddings (from config)
    ↓
Store in LanceDB
    ↓
Ready for querying
```

## Output

### Raw Data

Extracted pages are saved to:

```
~/.local/share/openground/raw_data/{library}/
```

Each page becomes a JSON file with:

```json
{
    "url": "https://docs.example.com/guide/intro",
    "title": "Introduction",
    "content": "Full page content...",
    "library": "example-docs"
}
```

### Database

Data is stored in LanceDB at:

```
{db_path}/{table_name}/
```

Default: `~/.local/share/openground/lancedb/documents/`

The database contains:

-   **Vector embeddings**: For semantic search
-   **Full text content**: For BM25 keyword search
-   **Metadata**: URL, library name, chunk index

## Configuration

### Extraction Settings

```bash
openground config set extraction.concurrency_limit 50
```

### Ingestion Settings

```bash
openground config set ingestion.batch_size 32
openground config set ingestion.chunk_size 1000
openground config set ingestion.chunk_overlap 200
openground config set ingestion.embedding_model sentence-transformers/all-MiniLM-L6-v2
openground config set ingestion.embedding_dimensions 384
```

See [Configuration](../configuration.md) for more details.

## Performance

The `add` command performance depends on:

-   **Extraction**: Number of pages, concurrency limit, network speed
-   **Ingestion**: Number of pages, chunk size, batch size, hardware

Typical performance on a modern laptop:

-   **Extraction**: ~50-200 pages per minute (depends on site)
-   **Ingestion**: ~100-500 chunks per second
-   **Total time**: ~1000 pages in 10-20 minutes

The embedding model downloads automatically on first use (~80MB) and is cached locally.

## Next Steps

After adding a library:

1. **Verify it was added**: [`openground ls`](list-libraries.md)
2. **Query your docs**: [`openground query "search" --library NAME`](query.md)
3. **Setup MCP**: [MCP Integration](../mcp-integration.md) for AI agents

## Troubleshooting

### Extraction Fails

If extraction times out or fails:

-   Try reducing concurrency limit in config: `openground config set extraction.concurrency_limit 10`
-   Check that the sitemap URL is valid and accessible
-   Some sites may block automated scraping
-   Verify your internet connection

### Ingestion is Slow

First-time ingestion downloads the embedding model (~80MB). Subsequent runs will be faster.

To speed up ingestion:

-   Increase batch size: `openground config set ingestion.batch_size 64` (if you have enough memory)
-   Use a smaller embedding model
-   Reduce chunk size (fewer chunks to process)

### Out of Memory During Ingestion

Reduce batch size in your config:

```bash
openground config set ingestion.batch_size 8
```

Then re-run the command (extraction won't re-run if raw data already exists).

### Some Pages Not Extracted

-   Check that the sitemap URL is correct
-   Verify your filter keywords aren't too restrictive
-   Some pages in the sitemap may not be accessible

### Invalid Sitemap URL

Make sure you're using the sitemap XML URL, not the main site URL. Check:

-   `https://example.com/sitemap.xml`
-   `https://example.com/sitemap_index.xml`
-   Look in `https://example.com/robots.txt` for the sitemap URL

### Library Already Exists

If you try to add a library that already exists, ingestion will add new vectors alongside existing ones. To completely replace:

```bash
# Remove existing library
openground rm OLD_NAME -y

# Add fresh version
openground add -s URL -l OLD_NAME -y
```

## See Also

-   [extract](extract.md) - Extract documentation separately
-   [ingest](ingest.md) - Ingest extracted files separately
-   [query](query.md) - Search your documentation
-   [ls](list-libraries.md) - List all libraries
-   [Commands Overview](index.md) - All commands
-   [Configuration](../configuration.md) - Customize settings
