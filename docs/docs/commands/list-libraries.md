# ls (list-libraries)

List documentation libraries managed by Openground.

## Embedded Libraries

List libraries that have been processed and are stored in the database, ready for querying.

### Usage

```bash
openground ls
```

Alias: `openground list-libraries`

### Description

The `ls` command displays all documentation libraries currently stored in the local database. It output a simple list of library names that you can use with the `--library` flag in other commands.

### Examples

```bash
openground ls
```

Example output:
```
databricks
python-docs
stripe-docs
```

## List Raw Libraries

List libraries that have been extracted but not yet embedded into the database.

### Usage

```bash
openground list-raw-libraries
```

### Description

The `list-raw-libraries` command scans your raw data directory and lists the names of libraries that have been extracted (using `extract`, `extract-git`, or the first half of `add`).

This is useful if you want to:
- See what you've already downloaded but haven't indexed yet.
- Re-embed a library with different settings.

### Examples

```bash
openground list-raw-libraries
```

Example output:
```
Available libraries in raw_data:
  - databricks
  - fastmcp
  - openground
```

## Related Commands

- **Query a library**: [`openground query "search" --library NAME`](query.md)
- **Remove a library**: [`openground rm NAME`](remove-library.md)
- **Embed a raw library**: [`openground embed NAME`](embed.md)
- **Add a new library**: [`openground add NAME --source URL`](add.md)

## See Also

- [rm](remove-library.md) - Remove a library from the database
- [query](query.md) - Search embedded libraries
- [embed](embed.md) - Index raw documentation
