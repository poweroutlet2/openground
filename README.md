 
# openground CLI

Unified CLI for extracting docs, ingesting into LanceDB, and running hybrid search.

## Install

```bash
uv pip install -e .
```

This installs the `openground` command entrypoint.

## Commands

### Extract

Fetch and parse pages from the sitemap.

```bash
openground extract \
  --sitemap-url https://docs.databricks.com/aws/en/sitemap.xml \
  --concurrency-limit 50 \
  --collection-title Databricks \
  --output-dir raw_data/docs/Databricks \
  -f docs -f documentation -f blog
```

Flags:
- `--sitemap-url` / `-s`: root sitemap URL.
- `--concurrency-limit` / `-c`: max concurrent requests.
- `--collection-title` / `-t`: label for the docs collection.
- `--output-dir` / `-o`: where extracted JSON files are written (default `raw_data/docs/{collection_title}`).
- `--filter-keyword` / `-f`: repeatable; keywords to keep URLs (e.g., `-f docs -f blog`).

### Ingest

Chunk documents, embed, and load into LanceDB.

```bash
openground ingest \
  --data-dir raw_data/docs/Databricks \
  --db-path lancedb_data \
  --table-name documents \
  --chunk-size 1000 \
  --chunk-overlap 200 \
  --batch-size 32
```

### Query

Hybrid search (semantic + BM25).

```bash
openground query "how to connect" \
  --db-path lancedb_data \
  --table-name documents \
  --top-k 5
```

Optional:
- `--collection-title` / `-c`: filter by collection title.

## Notes

- Default output dir for extract is `raw_data/docs/{collection_title}`.
- LanceDB data defaults to `lancedb_data`; table defaults to `documents`.
- Reinstall (`uv pip install -e .`) after CLI code changes to refresh the entrypoint. 
