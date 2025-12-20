# MCP Integration

Openground exposes its search capabilities to AI coding assistants through the Model Context Protocol (MCP). This allows your AI assistant to query documentation directly while helping you code.

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io) is a standard for connecting AI applications to data sources. With openground's MCP server, your AI assistant can:

- Search documentation across all ingested libraries
- Get detailed page content for deeper context
- List available documentation libraries
- Help you find relevant information without leaving your editor

## Quick Setup

### 1. Install Openground

```bash
pip install openground
# or
uv tool install openground
```

### 2. Ingest Documentation

```bash
openground add \
  --sitemap-url https://docs.example.com/sitemap.xml \
  --library example-docs \
  -y
```

### 3. Configure Your AI Assistant

Openground can auto-configure popular AI coding assistants:

#### Cursor

```bash
openground install-mcp --cursor
```

#### Claude Code

```bash
openground install-mcp --claude-code
```

#### OpenCode

```bash
openground install-mcp --opencode
```

#### Manual Configuration

To see the MCP config JSON without auto-installing:

```bash
openground install-mcp
```

This displays the configuration you need to add to your assistant's config file.

### 4. Restart Your Assistant

After configuration, restart your AI coding assistant to load the MCP server.

## Available Tools

The openground MCP server exposes three tools to AI agents:

### search_documents_tool

Search documentation using hybrid BM25 + semantic search.

**Parameters:**

- `query` (string, required): The search query
- `library` (string, optional): Filter to a specific library
- `top_k` (integer, optional): Number of results (default: 5)

**Returns:**

Ranked list of relevant documentation chunks with URLs and scores.

### list_libraries_tool

List all ingested documentation libraries.

**Parameters:** None

**Returns:**

List of library names with document counts and metadata.

### get_full_content_tool

Retrieve the full content of a specific documentation page.

**Parameters:**

- `url` (string, required): The URL of the page to retrieve
- `library` (string, required): The library containing the page

**Returns:**

Complete page content including title and text.

## Example Conversations

Once configured, you can interact with your AI assistant naturally:

### Searching Documentation

**You:** "How do I authenticate with the Stripe API?"

**AI:** *Uses search_documents_tool with query="Stripe API authentication"*

"According to the Stripe documentation, you authenticate by including your API key in the Authorization header..."

### Finding Specific Features

**You:** "Show me examples of using webhooks in the docs"

**AI:** *Uses search_documents_tool with query="webhook examples"*

"I found several webhook examples in the documentation..."

### Getting Full Context

**You:** "Can you show me the full page about rate limiting?"

**AI:** *Uses search_documents_tool to find the page, then get_full_content_tool to retrieve it*

"Here's the complete rate limiting documentation..."

## Configuration Details

### Cursor Configuration

Openground adds configuration to `~/.cursor/config.json`:

```json
{
  "mcpServers": {
    "openground": {
      "command": "openground-mcp",
      "args": []
    }
  }
}
```

### Claude Code Configuration

Configuration goes in the Claude desktop app settings under MCP servers.

### Manual Configuration

For other MCP-compatible clients, use this configuration:

```json
{
  "mcpServers": {
    "openground": {
      "command": "openground-mcp",
      "args": []
    }
  }
}
```

Replace `openground-mcp` with the full path if needed:

```bash
which openground-mcp
```

## Advanced Configuration

### Custom Database Path

If you've configured a custom database path:

```bash
openground config set db_path /custom/path/to/lancedb
```

The MCP server automatically uses the same configuration file, so no additional setup is needed.

### Multiple Configuration Profiles

To use different configurations for different projects, set `XDG_CONFIG_HOME`:

```bash
export XDG_CONFIG_HOME=~/project-a/.config
openground config set db_path ~/project-a/data/lancedb
```

Then configure the MCP server to use the same environment variable.

## Verifying Setup

### 1. Check MCP Server

Test that the MCP server runs:

```bash
openground-mcp
```

This should start the server. Press Ctrl+C to stop.

### 2. Check Libraries

Ensure documentation is ingested:

```bash
openground ls
```

You should see at least one library listed.

### 3. Test Search

Try searching from the CLI:

```bash
openground query "test" --library your-library
```

If this works, the MCP server will work too.

### 4. Test in Your Assistant

Ask your AI assistant: "Can you search the openground documentation for 'authentication'?"

If MCP is configured correctly, the assistant should use the search tool.

## Troubleshooting

### MCP Server Not Found

If your assistant can't find `openground-mcp`:

```bash
# Find the full path
which openground-mcp

# Use full path in config
{
  "command": "/full/path/to/openground-mcp"
}
```

### No Results from Search

Check that libraries are ingested:

```bash
openground ls
```

If empty, ingest some documentation:

```bash
openground add -s URL -l NAME -y
```

### Permission Errors

Ensure the MCP server can access your database:

```bash
openground config get db_path
ls -la /path/to/db
```

### Assistant Not Using Tools

After configuration:

1. Restart your AI assistant completely
2. Check the assistant's logs for MCP errors
3. Try explicitly asking: "Use the openground search tool to find..."

### Config File Not Updated

If `--cursor` or `--claude-code` don't work:

1. Check the config file location: `openground install-mcp` shows the path
2. Manually add the config
3. Ensure you have write permissions

## Library Workflow

### Adding New Documentation

When you add new documentation libraries, they're immediately available to the MCP server:

```bash
# Add a new library
openground add -s URL -l new-docs -y

# No restart needed - AI can now search it
```

### Updating Documentation

To update existing documentation:

```bash
# Remove old version
openground rm old-docs -y

# Extract and ingest new version
openground add -s URL -l old-docs -y
```

The MCP server uses the database, so updates are immediate.

### Multiple Libraries

The AI can search across all ingested libraries or filter to specific ones:

```bash
# Ingest multiple libraries
openground add -s https://docs.stripe.com/sitemap.xml -l stripe -y
openground add -s https://docs.databricks.com/sitemap.xml -l databricks -y

# AI can search both or filter to one
```

## Best Practices

### Organize Libraries

Use descriptive library names:

```bash
# Good
openground add -s URL -l stripe-api-docs -y
openground add -s URL -l react-v18-docs -y

# Less clear
openground add -s URL -l docs1 -y
openground add -s URL -l docs2 -y
```

### Keep Documentation Updated

Set up a cron job or GitHub Action to refresh documentation:

```bash
#!/bin/bash
# update-docs.sh
openground rm my-docs -y
openground add -s URL -l my-docs -y
```

### Use Filters During Extraction

Only ingest relevant documentation:

```bash
openground add \
  -s https://docs.example.com/sitemap.xml \
  -l example \
  -f docs -f api -f guide \
  -y
```

This keeps the database focused and search results relevant.

### Monitor Database Size

Check library sizes periodically:

```bash
openground ls
du -sh ~/.local/share/openground/lancedb/
```

Remove unused libraries to save space:

```bash
openground rm unused-library -y
```

## Privacy and Security

### Local Processing

- All data is stored locally on your machine
- Embeddings are generated using a local model (no API calls)
- Searches run locally against your LanceDB database
- No data is sent to external servers

### MCP Security

- The MCP server only exposes read-only search operations
- It cannot modify or delete your database
- It uses the same permissions as your user account
- Communication between assistant and server is local

### Sensitive Documentation

If you're indexing internal or proprietary documentation:

1. **Store database securely**: Use an encrypted directory
2. **Limit library scope**: Only ingest what you need
3. **Clean up after**: Remove libraries when no longer needed
4. **Review AI queries**: Be mindful of what you ask the AI

## Performance

### Search Speed

- Typical query: 50-200ms
- Larger databases (10,000+ chunks): May take longer
- Embedding model loads once at startup (~1-2 seconds)

### Memory Usage

The MCP server keeps embeddings in memory:

- Default model: ~80MB
- Larger models: Up to 500MB
- Database: Minimal memory footprint (uses disk-based storage)

### Optimization

For faster searches:

```bash
# Use smaller model
openground config set embedding_model sentence-transformers/all-MiniLM-L6-v2

# Reduce top_k
openground config set query.top_k 3
```

## See Also

- [Getting Started](getting-started.md) - Install and configure openground
- [Commands](commands/index.md) - CLI reference
- [Configuration](configuration.md) - Customize settings
- [Model Context Protocol](https://modelcontextprotocol.io) - Learn about MCP

