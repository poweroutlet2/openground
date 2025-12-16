# ls (list-libraries)

List all ingested documentation libraries.

## Usage

```bash
openground ls
```

Alias: `openground list-libraries`

## Description

The `ls` command displays all documentation libraries currently stored in the database. For each library, it shows:

- **Library name**: The identifier used in commands
- **Document count**: Number of documents/chunks indexed
- **Last modified**: When the library was last updated

This helps you see what documentation is available for querying.

## Arguments

None. This command takes no arguments.

## Examples

### List All Libraries

```bash
openground ls
```

Example output:

```
Ingested Libraries:

1. databricks
   Documents: 1,247 chunks
   Last updated: 2024-12-15 14:23:45

2. stripe-docs
   Documents: 892 chunks
   Last updated: 2024-12-14 09:15:22

3. python-docs
   Documents: 3,456 chunks
   Last updated: 2024-12-10 16:42:11

Total: 3 libraries
```

### No Libraries

If no libraries are ingested:

```bash
openground ls
```

Output:

```
No libraries found in the database.

To add a library:
  openground extract-and-ingest --sitemap-url URL --library NAME -y
```

## Use Cases

### Before Querying

Check what libraries are available before searching:

```bash
openground ls
openground query "authentication" --library databricks
```

### After Ingestion

Verify that ingestion completed successfully:

```bash
openground ingest --library my-docs
openground ls
```

### Library Management

See what's taking up space before cleanup:

```bash
openground ls
openground rm old-library -y
```

## Understanding the Output

### Document Count

The "chunks" count represents how many text chunks were created during ingestion. This depends on:

- Number of pages extracted
- Chunk size setting
- Document lengths

A library with 1,000 chunks might represent:

- 100 pages with 10 chunks each
- 1,000 short pages with 1 chunk each
- 50 long pages with 20 chunks each

### Last Updated

This timestamp shows when the library was last modified. Use it to:

- Track when documentation was indexed
- Identify stale documentation that needs updating
- Verify that recent ingestion jobs completed

## Related Commands

After viewing libraries:

- **Query a library**: [`openground query "search" --library NAME`](query.md)
- **Remove a library**: [`openground rm NAME`](remove-library.md)
- **Add a new library**: [`openground extract-and-ingest -s URL -l NAME`](index.md)

## Configuration

The `ls` command uses your configured database path:

```bash
openground config get db_path
```

See [Configuration](../configuration.md) for details.

## Troubleshooting

### No Libraries Shown (But You Ingested Some)

Check that you're using the correct database path:

```bash
openground config show
```

If you changed `db_path` after ingestion, your old data might be in a different location.

### Wrong Library Count

If the count seems off:

- Re-ingest the library: `openground ingest --library NAME`
- Check the raw data exists: `ls ~/.local/share/openground/raw_data/NAME/`

## See Also

- [rm](remove-library.md) - Remove a library
- [query](query.md) - Search libraries
- [ingest](ingest.md) - Add libraries
- [Configuration](../configuration.md) - Database settings

