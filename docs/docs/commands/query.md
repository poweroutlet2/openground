# query

Search ingested documentation using hybrid BM25 + semantic search.

## Usage

```bash
openground query "how to authenticate" --library example-docs
```

## Description

The `query` command searches your ingested documentation using hybrid search that combines:

1. **Semantic search**: Finds results based on meaning and context using vector embeddings
2. **BM25 full-text search**: Finds results based on keyword matching

Results are ranked by relevance and include source URLs, library names, and content snippets.

## Arguments

### Required

#### query

The search query (positional argument).

```bash
openground query "how to configure authentication"
```

Use natural language queries for best results. The semantic search understands context and meaning, not just keywords.

### Optional

#### `--library`, `-l`

Filter results to a specific library.

```bash
openground query "API keys" --library databricks
```

Without this flag, all ingested libraries are searched.

#### `--top-k`, `-k`

Number of results to return (default: 5, or from config).

```bash
openground query "search terms" --top-k 10
```

## Examples

### Basic Search

```bash
openground query "getting started"
```

Searches all libraries, returns top 5 results.

### Library-Specific Search

```bash
openground query "authentication" --library my-api-docs
```

### More Results

```bash
openground query "configuration options" --top-k 15
```

### Natural Language Queries

The semantic search understands meaning:

```bash
openground query "how do I set up API keys?"
openground query "troubleshooting connection issues"
openground query "best practices for error handling"
```

## Output Format

Results are displayed with:

- **Rank**: Result number
- **Title/Preview**: First line of content
- **Score**: Relevance score (0-1, higher is better)
- **Library**: Which documentation library
- **URL**: Source page URL
- **Content**: Relevant snippet

Example output:

```
Results for: "how to authenticate"

1. Authentication Overview (Score: 0.89)
   Library: my-api-docs
   URL: https://docs.example.com/auth/overview
   
   To authenticate with the API, you need to obtain an API key from your
   dashboard. Include the key in the Authorization header of each request...

2. API Key Management (Score: 0.82)
   Library: my-api-docs
   URL: https://docs.example.com/auth/api-keys
   
   API keys provide secure access to your resources. You can create and
   manage keys from the settings page. Each key can be scoped to specific...

[3 more results...]
```

## How Hybrid Search Works

Openground combines two search methods:

### Semantic Search (Vector Similarity)

- Uses embeddings to find contextually similar content
- Understands synonyms and related concepts
- Good for: Natural language queries, finding related content

Example: "authentication" matches "login", "credentials", "access control"

### BM25 (Keyword Search)

- Traditional full-text search based on term frequency
- Finds exact keyword matches and variations
- Good for: Specific terms, acronyms, function names

Example: "JWT" matches documents containing "JWT" exactly

### Combined Ranking

Results from both methods are merged and re-ranked to give you the most relevant content.

## Search Tips

### Use Natural Language

```bash
# Good - natural language
openground query "how do I deploy to production?"

# Also works - keywords
openground query "deployment production"
```

### Be Specific When Needed

```bash
# Vague
openground query "settings"

# Specific
openground query "database connection settings"
```

### Use Library Filters

If you have multiple libraries ingested:

```bash
openground query "webhooks" --library stripe-docs
```

### Adjust Result Count

For broad topics, get more results:

```bash
openground query "configuration" --top-k 20
```

## Configuration

Set default number of results:

```bash
openground config set query.top_k 10
```

CLI flags override config values. See [Configuration](../configuration.md) for more details.

## MCP Integration

The same search functionality is available to AI agents through the MCP server. Configure it with:

```bash
openground install-mcp --cursor
```

See [MCP Integration](../mcp-integration.md) for details.

## Advanced Usage

### Combining with Other Tools

Pipe results to other tools:

```bash
openground query "API reference" -l docs --top-k 20 | grep "POST"
```

### Programmatic Access

If you need programmatic access, consider using the Python API directly or the MCP server.

## Troubleshooting

### No Results

- Check that the library is ingested: `openground ls`
- Try broader search terms
- Try without `--library` filter to search all libraries

### Poor Quality Results

- Try more specific queries
- Adjust chunking parameters and re-ingest (see [ingest](ingest.md))
- Consider using a better embedding model (see [Configuration](../configuration.md#embedding-model-settings))

### Results Missing Expected Content

- Check if the page was extracted: Look in `~/.local/share/openground/raw_data/{library}/`
- The content might be in a different chunk: Increase `--top-k`
- Re-extract with different filters: `openground extract -f keyword`

## See Also

- [ingest](ingest.md) - Ingest documentation before querying
- [list-libraries](list-libraries.md) - See available libraries
- [Configuration](../configuration.md) - Customize search settings
- [MCP Integration](../mcp-integration.md) - Query from AI agents

