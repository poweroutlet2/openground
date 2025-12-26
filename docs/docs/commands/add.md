# add

Extract documentation pages from a source and embed them into the database in one step.

## Usage

```bash
# Using a sitemap
openground add example-docs \
  --source https://docs.example.com/sitemap.xml \
  -f docs -f guide \
  -y

# Using a git repository
openground add example-docs \
  --source https://github.com/example/repo.git \
  --docs-path docs/ \
  -y
```

## Description

The `add` command combines [`extract`](extract.md) (or `extract-git`) and [`embed`](embed.md) into a single operation. It intelligently detects the source type (sitemap or git) based on the URL provided to `--source`, or looks up the configuration in the built-in `sources.json` file.

If a library is found in `sources.json`, Openground automatically uses the predefined source URL, filter keywords, or documentation paths.

### Sitemap Source
1. Fetches the sitemap XML from the provided URL.
2. Parses all page URLs from the sitemap (including nested sitemaps).
3. Downloads each page concurrently using aiohttp.
4. Extracts main content using trafilatura.
5. Saves each page as a JSON file in the raw data directory.

### Git Source
1. Clones the repository using a shallow clone.
2. Uses sparse checkout to only fetch the specified documentation paths.
3. Walks the documentation directory and reads markdown/text files.
4. Saves each file as a JSON document in the raw data directory.

### Embedding (Shared)
1. Loads the JSON files and splits them into chunks.
2. Generates embeddings using a local sentence-transformer model.
3. Stores vectors and creates a BM25 full-text search index in LanceDB.

This is the fastest way to get documentation indexed and ready for querying.

!!! tip "When to use `add` vs separate commands"
    Use `add` when you want to extract and embed in one go. Use separate [`extract`](extract.md) and [`embed`](embed.md) commands when you want to:
    - Extract once, then re-embed with different chunking strategies.
    - Review extracted content before indexing.
    - Keep raw data for backup or analysis.
    - Extract from multiple sources before embedding together.

## Arguments

### Required

#### `library` (Positional)
The name of the library/framework. This determines where the extracted files are saved and how the library is identified in the database.

```bash
openground add my-project --source URL -y
```

Files are saved to `~/.local/share/openground/raw_data/my-project/` and indexed under the name `my-project`.

### Optional

#### `--source`, `-s`
The root sitemap URL or Git repo URL to crawl. If not provided, Openground attempts to look up the library name in its built-in `sources.json` file.

```bash
openground add example -s https://docs.example.com/sitemap.xml
```

If the library is in `sources.json` (like `lancedb`, `fastapi`, `pydantic`), you can just run:

```bash
openground add fastapi -y
```

#### `--docs-path`, `-d` (Git only)
Path to documentation within a git repo. Specify multiple times for multiple paths (e.g., `-d docs/ -d wiki/`). Defaults to `docs/` if not specified.

```bash
openground add example -s https://github.com/example/repo.git -d docs/ -d wiki/
```

#### `--filter-keyword`, `-f` (Sitemap only)
Filter URLs to only extract pages containing specific keywords. Can be specified multiple times.

```bash
# Only extract URLs containing "docs" OR "documentation"
openground add -s URL -l NAME -f docs -f documentation -y
```

#### `--yes`, `-y`
Skip the confirmation prompt between extraction and ingestion.

```bash
openground add -s URL -l NAME -y
```

## Embedding Parameters

The `add` command uses configuration values for embedding parameters. These can be set in your config file:

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
    Unlike the separate `embed` command, `add` does not support CLI flags for chunking parameters. If you need custom chunking for a specific run, set the values in your config file before running `add`, or use separate `extract` and `embed` commands.

## Examples

### Basic Sitemap Usage
```bash
openground add python-docs -s https://docs.python.org/3/sitemap.xml -y
```

### Basic Git Usage
```bash
openground add my-lib -s https://github.com/user/my-lib.git -y
```

### Filtered Sitemap Extraction
```bash
openground add example-docs -s https://docs.example.com/sitemap.xml -f tutorial -f guide -y
```

### Git Extraction with Custom Paths
```bash
openground add example-docs -s https://github.com/example/repo.git -d documentation/ -d spec/ -y
```

## See Also
- [extract](extract.md) - Extract documentation separately
- [extract-git](extract-git.md) - Extract from git repo separately
- [embed](embed.md) - Embed extracted files separately
- [query](query.md) - Search your documentation
- [Configuration](../configuration.md) - Customize settings
