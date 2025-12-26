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

#### Options

- `--defaults`: Show only hardcoded defaults, ignoring your user configuration file.

```bash
openground config show --defaults
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
openground config get ingestion.embedding_model
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

### path

Display the path to the configuration file.

```bash
openground config path
```

### reset

Delete the configuration file and restore all defaults.

```bash
openground config reset
```

!!! warning
    This permanently deletes your config file. Database and raw data are not affected.

## Configuration Keys

See the [Configuration](../configuration.md) page for detailed information about each setting.

### Quick Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `db_path` | string | `~/.local/share/openground/lancedb` | Database directory |
| `table_name` | string | `documents` | Database table name |
| `raw_data_dir` | string | `~/.local/share/openground/raw_data` | Raw data directory |
| `extraction.concurrency_limit` | integer | `50` | Max concurrent requests |
| `ingestion.batch_size` | integer | `32` | Embedding batch size |
| `ingestion.chunk_size` | integer | `1000` | Chunk size in characters |
| `ingestion.chunk_overlap` | integer | `200` | Overlap between chunks |
| `ingestion.embedding_model` | string | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model |
| `ingestion.embedding_dimensions` | integer | `384` | Embedding vector size |
| `query.top_k` | integer | `5` | Default result count |

## Examples

### Change Chunking Settings

```bash
openground config set ingestion.chunk_size 1500
openground config set ingestion.chunk_overlap 300
```

### Use a Better Embedding Model

```bash
openground config set ingestion.embedding_model sentence-transformers/all-mpnet-base-v2
openground config set ingestion.embedding_dimensions 768
```

!!! note
    After changing the embedding model, you must re-embed all libraries.

## See Also

- [Configuration](../configuration.md) - Detailed configuration reference
- [Commands Overview](index.md) - All commands
