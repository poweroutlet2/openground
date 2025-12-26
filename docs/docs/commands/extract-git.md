# extract-git

Extract documentation from a git repository using shallow clone and sparse checkout.

## Usage

```bash
openground extract-git \
  --repo-url https://github.com/example/repo.git \
  --docs-path docs/ \
  --library example-docs
```

## Description

The `extract-git` command downloads documentation from a git repository. It is designed to be efficient by only fetching the necessary files without downloading the entire repository history.

It performs the following steps:
1. **Shallow Clone**: Initializes a local repository and adds the remote.
2. **Sparse Checkout**: Configures git to only fetch the specified documentation paths.
3. **Download**: Fetches the content of the specified paths at the default branch.
4. **Parse**: Walks the downloaded files, reading markdown and text files.
5. **Save**: Converts each file into a JSON document and saves it to the raw data directory.

The extracted JSON files can then be embedded into the database using the [`embed`](embed.md) command.

## Arguments

### Required

#### `--repo-url`, `-r`
The URL of the git repository to extract from.

```bash
openground extract-git -r https://github.com/fastmcp/fastmcp.git -d docs/ -l fastmcp
```

#### `--docs-path`, `-d`
Path to the documentation directory within the repository. You can specify this multiple times for multiple directories. Use `/` for the whole repository.

```bash
openground extract-git -r URL -d docs/ -d wiki/ -l NAME
```

#### `--library`, `-l`
The name of the library/framework. This determines where the extracted files are saved.

```bash
openground extract-git -r URL -d docs/ -l my-project
```

Files are saved to `~/.local/share/openground/raw_data/my-project/`.

## Examples

### Basic Extraction
```bash
openground extract-git \
  --repo-url https://github.com/example/repo.git \
  --docs-path docs/ \
  --library example-docs
```

### Multiple Documentation Paths
```bash
openground extract-git \
  --repo-url https://github.com/example/repo.git \
  --docs-path docs/ \
  --docs-path guides/ \
  --library example-docs
```

### Extracting Everything
```bash
openground extract-git \
  --repo-url https://github.com/example/repo.git \
  --docs-path / \
  --library example-docs
```

## Output

Extracted pages are saved to:

```
~/.local/share/openground/raw_data/{library}/
```

Each document becomes a JSON file with:

```json
{
    "url": "repo_url/blob/main/docs/guide.md",
    "title": "guide.md",
    "content": "Full file content...",
    "library": "example-docs"
}
```

## See Also
- [add](add.md) - Extract and embed in one step (supports git)
- [embed](embed.md) - Process extracted files
- [Commands Overview](index.md) - All commands

