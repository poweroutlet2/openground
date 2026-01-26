# Claude Code Agent for Openground Documentation Search

Openground includes a custom Claude Code agent that searches official documentation without polluting your main conversation context.

## What is the Openground Docs Search Agent?

The `openground-docs-search` agent is a specialized subagent that:
- Has access to openground's 3 MCP tools for documentation search
- Runs in an isolated context to avoid cluttering your main conversation
- Automatically searches your local openground vector database
- Returns focused documentation results with sources

## Installation

### Step 1: Ensure Openground MCP is Installed

```bash
openground install-mcp --claude-code
```

### Step 2: Install the Agent

Copy the agent definition to your Claude Code agents directory:

```bash
# Create the agents directory if it doesn't exist
mkdir -p ~/.claude/agents

# Copy the agent file
cp .claude/agents/openground-docs-search.md ~/.claude/agents/
```

### Step 3: Restart Claude Code

Quit and restart Claude Code for the agent to be available.

## Usage

The agent will be automatically invoked when you ask about library APIs, framework concepts, or need official documentation references.

### Example Queries

- "How do I use React useEffect hook?"
- "What's the difference between FastAPI's Query() and Path()?"
- "Show me how to create a Django model"
- "What are the available methods in pandas DataFrame?"

### Manual Invocation

You can also explicitly request the agent:

> "Use the openground-docs-search agent to find information about async/await in JavaScript"

## How It Works

The agent follows this workflow:

1. **Lists available libraries** - Confirms what documentation is in your openground database
2. **Searches documentation** - Uses semantic search to find relevant sections
3. **Presents results** - Shows relevant snippets with source URLs
4. **Fetches full content** - Gets complete documents when needed

## Agent Configuration

The agent definition (`.claude/agents/openground-docs-search.md`) includes:

```yaml
---
name: openground-docs-search
description: Search official framework and library documentation from openground's local vector database.
tools: mcp__openground__list_libraries_tool, mcp__openground__search_documents_tool, mcp__openground__get_full_content_tool
model: sonnet
---
```

The agent uses:
- **sonnet** model by default for good balance of speed and intelligence
- Only openground's MCP tools (no file system access)
- Read-only operations for safety

## Troubleshooting

### Agent not found

Make sure the agent file is in the correct location:
- Global: `~/.claude/agents/openground-docs-search.md`
- Project-level: `.claude/agents/openground-docs-search.md`

### No search results

1. Verify openground has documentation installed:
   ```bash
   openground list
   ```

2. Add documentation if needed:
   ```bash
   openground add library-name --source https://github.com/example/example.git --docs-path docs/ --version v1.0.0 -y
   ```

### MCP tools not available

Ensure openground MCP server is installed:
```bash
openground install-mcp --claude-code
```
