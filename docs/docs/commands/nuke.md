# nuke

Delete all data from raw_data and/or LanceDB directories.

## Overview

The `nuke` commands provide a way to completely delete all data from your Openground installation. These commands are useful for:

- Starting fresh with a clean slate
- Freeing up disk space
- Removing all data before changing embedding backends or models

!!! danger
    These commands are **destructive and irreversible**. All deleted data must be re-extracted and re-embedded from the original sources.

## Commands

### nuke all

Delete all files in both raw_data and LanceDB directories.

#### Usage

```bash
openground nuke all
```

#### Description

The `nuke all` command deletes everything:

- All raw data libraries (extracted JSON files)
- All embedded libraries (vector database)

This completely resets your Openground installation to an empty state.

#### Options

##### `--yes`, `-y`

Skip the confirmation prompt. Use with caution!

```bash
openground nuke all --yes
```

#### Examples

##### Interactive Deletion

```bash
openground nuke all
```

You'll see a summary and be prompted to confirm:

```
⚠️  This will permanently delete ALL data:
  • Raw data: 5 libraries in ~/.local/share/openground/raw_data
  • Embeddings: 3 libraries in ~/.local/share/openground/lancedb

💡 Tip: Run 'openground list-raw-libraries' and 'openground list-libraries' to see what will be deleted.

Are you sure you want to delete ALL data? This cannot be undone! [y/N]: y
✅ Deleted raw data directory: ~/.local/share/openground/raw_data
✅ Deleted LanceDB directory: ~/.local/share/openground/lancedb

✅ Deleted all data (5 raw libraries, 3 embedded libraries).
```

##### Non-Interactive Deletion

For scripts or automation:

```bash
openground nuke all --yes
```

### nuke raw_data

Delete all files in the raw_data directory.

#### Usage

```bash
openground nuke raw_data
```

#### Description

The `nuke raw_data` command deletes only the raw extracted data:

- All raw data libraries (extracted JSON files)
- Does not affect embedded libraries in the database

This is useful if you want to keep your embeddings but remove the raw files to free up space.

#### Options

##### `--yes`, `-y`

Skip the confirmation prompt.

```bash
openground nuke raw_data --yes
```

#### Examples

##### Interactive Deletion

```bash
openground nuke raw_data
```

Example output:

```
⚠️  This will permanently delete ALL raw data:
  • 5 libraries in ~/.local/share/openground/raw_data

💡 Tip: Run 'openground list-raw-libraries' to see what will be deleted.

Are you sure you want to delete ALL raw data? This cannot be undone! [y/N]: y
✅ Deleted raw data directory: ~/.local/share/openground/raw_data

✅ Deleted 5 raw libraries.
```

### nuke embeddings

Delete all files in the LanceDB directory.

#### Usage

```bash
openground nuke embeddings
```

#### Description

The `nuke embeddings` command deletes only the embedded data:

- All embedded libraries (vector database)
- Does not affect raw data files

This is useful if you want to keep your raw extracted files but need to re-embed everything (e.g., after changing embedding backend or model).

#### Options

##### `--yes`, `-y`

Skip the confirmation prompt.

```bash
openground nuke embeddings --yes
```

#### Examples

##### Interactive Deletion

```bash
openground nuke embeddings
```

Example output:

```
⚠️  This will permanently delete ALL embeddings:
  • 3 libraries in ~/.local/share/openground/lancedb

💡 Tip: Run 'openground list-libraries' to see what will be deleted.

Are you sure you want to delete ALL embeddings? This cannot be undone! [y/N]: y
✅ Deleted LanceDB directory: ~/.local/share/openground/lancedb

✅ Deleted 3 embedded libraries.
```

## Safety Features

All nuke commands include:

- **Library counts**: Shows how many libraries will be deleted before confirmation
- **Confirmation prompts**: Requires explicit confirmation unless `--yes` flag is used
- **Helpful hints**: Suggests running list commands to see what will be deleted
- **Clear warnings**: Emphasizes that deletion is irreversible

## When to Use

### nuke all

Use when you want to completely start over:

- Changing embedding backend or model
- Freeing up maximum disk space
- Resetting your entire Openground installation

### nuke raw_data

Use when you want to keep embeddings but remove raw files:

- Raw files are taking up too much space
- You've already ingested everything and don't need the raw JSON files
- You can always re-extract from the original sources

### nuke embeddings

Use when you want to keep raw files but re-embed everything:

- Changed embedding backend (e.g., from sentence-transformers to fastembed)
- Changed embedding model
- Need to re-index with different chunk sizes or other settings

## Related Commands

- **List libraries**: [`openground ls`](list-libraries.md) - See what's in the database
- **List raw libraries**: [`openground list-raw-libraries`](list-libraries.md#list-raw-libraries) - See what raw data exists
- **Remove a single library**: [`openground rm NAME`](remove-library.md) - Delete one library instead of all
- **Re-embed after nuking**: [`openground embed LIBRARY`](embed.md) - Re-index raw data

## See Also

- [Configuration](../configuration.md) - Database and storage paths
- [rm](remove-library.md) - Remove individual libraries
- [embed](embed.md) - Re-embed after deletion

