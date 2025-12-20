# extract

Extract documentation pages from a website's sitemap and save them as JSON files.

## Usage

```bash
openground extract \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f docs -f guide
```

## Description

The `extract` command downloads and parses documentation pages from a sitemap. It:

1. Fetches the sitemap XML from the provided URL
2. Parses all page URLs from the sitemap (including nested sitemaps)
3. Downloads each page concurrently using aiohttp
4. Extracts main content using trafilatura
5. Saves each page as a JSON file in the raw data directory

The extracted JSON files can then be ingested into the database using the [`ingest`](ingest.md) command.

## Arguments

### Required

#### `--sitemap-url`, `-s`

The URL of the sitemap XML file to extract from.

```bash
openground extract -s https://docs.databricks.com/aws/en/sitemap.xml -l databricks
```

Most documentation sites have a sitemap at `/sitemap.xml`, but some use different paths. Check the site's `robots.txt` file to find the sitemap URL.

#### `--library`, `-l`

The name of the library/framework. This determines where the extracted files are saved.

```bash
openground extract -s URL -l my-project
```

Files are saved to `~/.local/share/openground/raw_data/my-project/`.

### Optional

#### `--filter-keyword`, `-f`

Filter URLs to only extract pages containing specific keywords. Can be specified multiple times.

```bash
# Only extract URLs containing "docs" OR "documentation"
openground extract -s URL -l NAME -f docs -f documentation
```

This is useful for:

-   Excluding blog posts or marketing pages
-   Focusing on specific documentation sections
-   Reducing extraction time and storage

!!! tip
Start without filters to see what URLs are available, then re-run with filters if needed.

#### `--concurrency-limit`, `-c`

Maximum number of concurrent HTTP requests (default: 50, or from config).

```bash
openground extract -s URL -l NAME -c 20
```

Lower this if:

-   You're experiencing timeouts
-   The server is rate-limiting your requests
-   You have limited bandwidth

Higher values (up to 100) may be faster for large sites, but use more resources.

## Examples

### Basic Extraction

```bash
openground extract \
  --sitemap-url https://docs.python.org/3/sitemap.xml \
  --library python-docs
```

### Filtered Extraction

Extract only tutorial and guide pages:

```bash
openground extract \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -f tutorial -f guide -f getting-started
```

### Slow, Conservative Extraction

For servers that might rate-limit:

```bash
openground extract \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  --concurrency-limit 10
```

## Output

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

## Configuration

The concurrency limit can be set in your config file:

```bash
openground config set extraction.concurrency_limit 30
```

CLI flags override config values. See [Configuration](../configuration.md) for more details.

## Next Steps

After extraction:

1. **Ingest the data**: [`openground ingest --library NAME`](ingest.md)
2. **Or use the combined command**: [`openground add`](add.md) to do both steps at once

## Troubleshooting

### Extraction is Slow

-   Increase `--concurrency-limit` (try 100)
-   Check your internet connection
-   Some sites may have slow response times

### Some Pages Not Extracted

-   Check that the sitemap URL is correct
-   Verify your filter keywords aren't too restrictive
-   Some pages in the sitemap may not be accessible

### Timeouts

-   Reduce `--concurrency-limit` (try 10-20)
-   The server may be rate-limiting you
-   Try again later

### Invalid Sitemap URL

Make sure you're using the sitemap XML URL, not the main site URL. Check:

-   `https://example.com/sitemap.xml`
-   `https://example.com/sitemap_index.xml`
-   Look in `https://example.com/robots.txt` for the sitemap URL

## See Also

-   [ingest](ingest.md) - Process extracted files
-   [Commands Overview](index.md) - All commands
