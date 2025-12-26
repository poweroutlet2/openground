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

### 2. Embed Documentation

```bash
openground add example --source https://docs.example.com/sitemap.xml -y
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

The openground MCP server exposes several tools to AI agents:

### search_documents_tool

Search the official documentation knowledge base to answer user questions.

**Parameters:**

- `query` (string, required): The search query
- `library_name` (string, required): The name of the library to search in

**Returns:**

Ranked list of relevant documentation chunks with URLs and scores.

### list_libraries_tool

Retrieve a list of available documentation libraries/frameworks.

**Parameters:** None

**Returns:**

List of library names currently stored in the database.

### search_available_libraries_tool

Search for available documentation libraries by name.

**Parameters:**

- `search_term` (string, required): Term to search for in library names

**Returns:**

List of library names matching the search term.

### get_full_content_tool

Retrieve the full content of a documentation page.

**Parameters:**

- `url` (string, required): The URL of the page to retrieve

**Returns:**

Complete page content including title and source URL.

## Configuration Details

### Cursor Configuration

Openground adds configuration to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "openground": {
      "command": "openground-mcp"
    }
  }
}
```

### Claude Code Configuration

Openground uses the `claude mcp add` command to register the server with Claude Code.

### Manual Configuration

For other MCP-compatible clients, use this configuration:

```json
{
  "mcpServers": {
    "openground": {
      "command": "openground-mcp"
    }
  }
}
```

Replace `openground-mcp` with the full path if needed:

```bash
which openground-mcp
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

If empty, embed some documentation:

```bash
openground add example -s URL -y
```

## See Also

- [Getting Started](getting-started.md) - Install and configure openground
- [Commands](commands/index.md) - CLI reference
- [Configuration](configuration.md) - Customize settings
- [Model Context Protocol](https://modelcontextprotocol.io) - Learn about MCP
