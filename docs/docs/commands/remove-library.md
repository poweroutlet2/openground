# rm (remove)

Remove a documentation library from the database and optionally delete its raw files.

## Usage

```bash
openground rm databricks
```

Alias: `openground remove databricks`

## Description

The `rm` command deletes a library from the LanceDB database. This:

- Removes all vector embeddings for the library
- Deletes all chunks and metadata
- Frees up database storage

If you are running the command interactively (without the `--yes` flag), Openground will also offer to delete the raw JSON files from your storage.

!!! warning
    Deleting from the database is **irreversible**. If you also delete the raw files, you will need to re-extract the documentation from its source to get it back.

## Arguments

### Required

#### library
The name of the library to remove (positional argument).

```bash
openground rm my-old-docs
```

### Optional

#### `--yes`, `-y`
Skip the confirmation prompt. When this flag is used, only the database entries are removed; raw files are preserved.

```bash
openground rm databricks -y
```

## Examples

### Interactive Removal

```bash
openground rm stripe-docs
```

You'll be prompted to confirm:

```
Library: stripe-docs
  Chunks: 892
  Pages:  143
  Sample titles: Introduction, Authentication, API Reference

Are you sure you want to delete this library? [y/N]: y
✅ Deleted 892 chunks for library 'stripe-docs'.

Also delete raw files at ~/.local/share/openground/raw_data/stripe-docs? [y/N]: y
✅ Deleted raw library files at ~/.local/share/openground/raw_data/stripe-docs.
```

### Non-Interactive Removal

For scripts or when you want to keep the raw files for later re-embedding:

```bash
openground rm old-library -y
```

## Related Commands

- **List libraries**: [`openground ls`](list-libraries.md)
- **Embed a library**: [`openground embed NAME`](embed.md)
- **Add a new library**: [`openground add NAME --source URL`](add.md)

## See Also

- [ls](list-libraries.md) - List libraries before removing
- [embed](embed.md) - Re-embed after removal
- [Configuration](../configuration.md) - Database settings
