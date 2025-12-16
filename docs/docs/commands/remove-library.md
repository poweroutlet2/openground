# rm (remove-library)

Remove a documentation library from the database.

## Usage

```bash
openground rm databricks
```

Alias: `openground remove-library databricks`

## Description

The `rm` command deletes a library from the LanceDB database. This:

- Removes all vectors and embeddings for the library
- Deletes all chunks and metadata
- Frees up database storage

!!! warning
    This operation is **irreversible**. The library data is permanently deleted from the database.

!!! note
    This only removes the library from the database, not the raw JSON files. Raw data remains in `~/.local/share/openground/raw_data/{library}/` and can be re-ingested.

## Arguments

### Required

#### library

The name of the library to remove (positional argument).

```bash
openground rm my-old-docs
```

### Optional

#### `--yes`, `-y`

Skip the confirmation prompt.

```bash
openground rm databricks -y
```

Without `-y`, you'll be prompted to confirm:

```
Are you sure you want to remove library 'databricks'? [y/N]:
```

## Examples

### Interactive Removal

```bash
openground rm stripe-docs
```

You'll be prompted to confirm:

```
Are you sure you want to remove library 'stripe-docs'? [y/N]: y
✓ Library 'stripe-docs' removed successfully.
```

### Non-Interactive Removal

For scripts or when you're certain:

```bash
openground rm old-library -y
```

### Remove Multiple Libraries

```bash
openground rm library1 -y
openground rm library2 -y
openground rm library3 -y
```

## What Gets Deleted?

### Removed from Database

- All vector embeddings for the library
- All text chunks
- All metadata (URLs, titles, etc.)
- BM25 index entries

### NOT Removed

- **Raw JSON files**: Still in `~/.local/share/openground/raw_data/{library}/`
- **Other libraries**: Only the specified library is affected
- **Configuration**: Your settings remain unchanged

## Re-ingesting After Removal

Since raw data is preserved, you can re-ingest the library:

```bash
# Remove library
openground rm docs -y

# Change chunking config
openground config set ingestion.chunk_size 1500

# Re-ingest with new settings
openground ingest --library docs
```

## Complete Removal (Including Raw Data)

To delete both the database entry and raw files:

```bash
# Remove from database
openground rm library-name -y

# Remove raw data
rm -rf ~/.local/share/openground/raw_data/library-name/
```

On Windows:

```bash
openground rm library-name -y
rmdir /s /q "%LOCALAPPDATA%\openground\raw_data\library-name"
```

## Use Cases

### Updating Documentation

```bash
# Remove old version
openground rm docs -y

# Extract and ingest new version
openground extract-and-ingest -s URL -l docs -y
```

### Cleaning Up Test Data

```bash
# Remove test libraries
openground rm test-lib1 -y
openground rm test-lib2 -y
openground rm experiment -y
```

### Trying Different Chunking

```bash
# Remove and re-ingest with different settings
openground rm library -y
openground config set ingestion.chunk_size 800
openground ingest --library library
```

### Freeing Space

```bash
# Check what's using space
openground ls

# Remove large unused libraries
openground rm unused-large-lib -y
```

## Verifying Removal

After removing, verify it's gone:

```bash
openground ls
```

The library should no longer appear in the list.

Try querying it:

```bash
openground query "test" --library removed-lib
```

Should return no results or indicate the library doesn't exist.

## Configuration

The `rm` command uses your configured database path:

```bash
openground config get db_path
```

See [Configuration](../configuration.md) for details.

## Safety Tips

1. **Check the library name**: Use `openground ls` to see exact names
2. **Use `-y` carefully**: Double-check library name when skipping confirmation
3. **Keep raw data**: Raw JSON files let you re-ingest if needed
4. **Backup important data**: If the library is critical, back up your database first

## Troubleshooting

### Library Not Found

```
Error: Library 'name' not found in database.
```

Check available libraries:

```bash
openground ls
```

### Permission Denied

If you get a permission error:

- Check that you have write access to the database directory
- Close any processes that might be accessing the database
- On Windows, ensure the database isn't locked

### Removal is Slow

For very large libraries (10,000+ chunks), removal can take a few seconds. This is normal.

## See Also

- [ls](list-libraries.md) - List libraries before removing
- [ingest](ingest.md) - Re-ingest after removal
- [extract](extract.md) - Re-extract if needed
- [Configuration](../configuration.md) - Database settings

