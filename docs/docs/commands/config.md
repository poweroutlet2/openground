# config

Manage openground configuration settings.

## Usage

```bash
openground config <subcommand> [args]
```

## Description

The `config` command provides subcommands to view and manage your openground configuration. Settings are stored in a JSON file and persist across sessions.

## Subcommands

### show

Display the current effective configuration.

```bash
openground config show
```

Example output:

```json
{
  "db_path": "/home/user/.local/share/openground/lancedb",
  "table_name": "documents",
  "extraction": {
    "concurrency_limit": 50
  },
  "ingestion": {
    "batch_size": 32,
    "chunk_size": 1000,
    "chunk_overlap": 200
  },
  "query": {
    "top_k": 5
  },
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_dimensions": 384
}
```

### get

Get the value of a specific configuration key.

```bash
openground config get <key>
```

Use dot notation for nested values:

```bash
openground config get db_path
openground config get ingestion.chunk_size
openground config get query.top_k
```

Example:

```bash
$ openground config get ingestion.chunk_size
1000
```

### set

Set a configuration value.

```bash
openground config set <key> <value>
```

Use dot notation for nested values:

```bash
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300
openground config set query.top_k 10
```

Example:

```bash
$ openground config set ingestion.chunk_size 1500
✓ Configuration updated: ingestion.chunk_size = 1500
```

### path

Display the path to the configuration file.

```bash
openground config path
```

Example output:

```
Configuration file: /home/user/.config/openground/config.json
```

### reset

Delete the configuration file and restore all defaults.

```bash
openground config reset
```

!!! warning
    This permanently deletes your config file. Database and raw data are not affected.

You'll be prompted to confirm:

```
Are you sure you want to reset the configuration to defaults? [y/N]: y
✓ Configuration reset to defaults.
```

## Configuration Keys

See the [Configuration](../configuration.md) page for detailed information about each setting.

### Quick Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `db_path` | string | `~/.local/share/openground/lancedb` | Database directory |
| `table_name` | string | `documents` | Database table name |
| `extraction.concurrency_limit` | integer | `50` | Max concurrent requests |
| `ingestion.batch_size` | integer | `32` | Embedding batch size |
| `ingestion.chunk_size` | integer | `1000` | Chunk size in characters |
| `ingestion.chunk_overlap` | integer | `200` | Overlap between chunks |
| `query.top_k` | integer | `5` | Default result count |
| `embedding_model` | string | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model |
| `embedding_dimensions` | integer | `384` | Embedding vector size |

## Examples

### View Current Config

```bash
openground config show
```

### Change Chunking Settings

```bash
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300
```

### Check a Specific Value

```bash
openground config get ingestion.chunk_size
```

### Change Database Location

```bash
openground config set db_path ~/my-custom-location/lancedb
```

### Use a Better Embedding Model

```bash
openground config set embedding_model sentence-transformers/all-mpnet-base-v2
openground config set embedding_dimensions 768
```

!!! note
    After changing the embedding model, you must re-ingest all libraries.

### Increase Query Results

```bash
openground config set query.top_k 15
```

### Find Config File

```bash
openground config path
```

### Reset Everything

```bash
openground config reset
```

## Configuration File Location

The config file is stored at:

- **Linux/macOS**: `~/.config/openground/config.json`
- **Windows**: `~/AppData/Local/openground/config.json`

Override by setting `XDG_CONFIG_HOME`:

```bash
export XDG_CONFIG_HOME=~/my-config-dir
openground config path
```

## Editing the Config File Directly

You can edit the JSON file directly, but using `openground config set` is recommended because it:

- Validates values
- Creates the file if it doesn't exist
- Handles dot notation
- Provides confirmation

If you do edit manually:

```bash
# Find the file
openground config path

# Edit it
nano ~/.config/openground/config.json

# Verify
openground config show
```

## Common Configuration Patterns

### Development Setup

Fast extraction, smaller chunks:

```bash
openground config set extraction.concurrency_limit 20
openground config set ingestion.chunk_size 800
openground config set ingestion.batch_size 16
```

### Production Setup

Better quality, more results:

```bash
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300
openground config set query.top_k 10
openground config set embedding_model sentence-transformers/all-mpnet-base-v2
openground config set embedding_dimensions 768
```

### Low-Memory Environment

```bash
openground config set extraction.concurrency_limit 10
openground config set ingestion.batch_size 8
openground config set ingestion.chunk_size 600
```

## Troubleshooting

### Config File Not Found

The config file is created automatically on first use. If it's missing:

```bash
openground config show
```

This creates it with defaults.

### Invalid JSON

If you edited the file manually and broke the JSON:

```bash
openground config reset
```

This deletes and recreates with defaults.

### Changes Not Taking Effect

Some settings require re-ingestion:

- `ingestion.chunk_size`
- `ingestion.chunk_overlap`
- `embedding_model`
- `embedding_dimensions`

After changing these:

```bash
openground ingest --library NAME
```

CLI flags override config values, so check that you're not passing conflicting flags.

### Permission Denied

If you can't write to the config directory:

- Check file permissions
- Try setting `XDG_CONFIG_HOME` to a writable location

## See Also

- [Configuration](../configuration.md) - Detailed configuration reference
- [Commands Overview](index.md) - All commands

