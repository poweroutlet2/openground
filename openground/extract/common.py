from typing import TypedDict, Callable
from pathlib import Path
import shutil
import json
import os
import asyncio
from urllib.parse import urlparse
from tqdm import tqdm
import nbformat


class ParsedPage(TypedDict):
    url: str
    library_name: str
    version: str
    title: str | None
    description: str | None
    last_modified: str | None
    content: str


def filter_documentation_files(
    docs_dir: Path, allowed_extensions: set[str] | None = None
) -> list[Path]:
    """
    Filter to relevant documentation files.

    Args:
        docs_dir: Directory to search for documentation files
        allowed_extensions: Set of file extensions to include (e.g., {".md", ".rst"}).
                          If None, defaults to common documentation formats.

    Returns:
        List of Path objects for documentation files
    """
    if allowed_extensions is None:
        # Default to most common doc formats
        allowed_extensions = {".md", ".rst", ".txt", ".mdx", ".ipynb", ".html", ".htm"}

    doc_files = []

    for root, dirs, files in os.walk(docs_dir):
        # Skip common non-doc directories
        dirs[:] = [
            d
            for d in dirs
            if d
            not in {
                "node_modules",
                "__pycache__",
                ".git",
                "images",
                "img",
                "assets",
                "static",
                "_build",
                "build",
                "dist",
                ".venv",
            }
        ]

        for file in files:
            file_path = Path(root) / file

            if file_path.suffix.lower() in allowed_extensions:
                # Skip hidden files
                if file.startswith("."):
                    continue

                # Always include README files (regardless of other filtering)
                if file.upper().startswith("README"):
                    doc_files.append(file_path)
                    continue

                # Skip common non-doc files
                if file not in {
                    "LICENSE",
                    "CHANGELOG",
                    "AUTHORS",
                }:
                    doc_files.append(file_path)

    return doc_files


def extract_notebook_content(file_path: Path) -> tuple[str, dict[str, str]]:
    """
    Extract content from Jupyter notebook.

    Args:
        file_path: Path to the .ipynb file

    Returns:
        Tuple of (content string, metadata dict)
    """
    with open(file_path, "r", encoding="utf-8") as f:
        nb = nbformat.read(f, as_version=4)

    content_parts = []
    metadata = {
        "title": nb.metadata.get("title", file_path.stem),
        "description": f"Jupyter notebook from {file_path.name}",
    }

    for cell in nb.cells:
        if cell.cell_type == "markdown":
            content_parts.append(cell.source)
        elif cell.cell_type == "code":
            # Include code cells with a marker
            content_parts.append(f"```python\n{cell.source}\n```")

    return "\n\n".join(content_parts), metadata


def remove_front_matter(content: str) -> tuple[str, dict[str, str]]:
    """
    Parse YAML front matter and return (content_without_front_matter, metadata).

    Args:
        content: Raw file content that may start with YAML front matter

    Returns:
        Tuple of (content without front matter, metadata dict from front matter)
    """
    if not content.startswith("---"):
        return content, {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return content, {}

    front_matter = parts[1]
    remaining_content = parts[2].strip()

    metadata = {}
    for line in front_matter.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip()

    return remaining_content, metadata


async def process_documentation_files(
    doc_files: list[Path],
    url_generator: Callable[[Path], str],
    library_name: str,
    version: str,
    default_description: str,
    base_path: Path | None = None,
) -> list[ParsedPage]:
    """
    Process documentation files and extract their content.

    This is a shared function used by both git and local_path extractors
    to process files with the same logic.

    Args:
        doc_files: List of file paths to process
        url_generator: Function that generates a URL for each file
        library_name: Name of the library
        version: Version string
        default_description: Default description for files without metadata
        base_path: Optional base path for generating relative descriptions

    Returns:
        List of ParsedPage objects
    """
    from openground.extract.sitemap import parse_html

    results: list[ParsedPage] = []

    for file_path in doc_files:
        try:
            file_url = url_generator(file_path)

            # Process different file types
            if file_path.suffix.lower() == ".ipynb":
                content, metadata = extract_notebook_content(file_path)
            elif file_path.suffix.lower() in (".html", ".htm"):
                with open(file_path, "r", encoding="utf-8") as f:
                    html = f.read()
                parsed = await asyncio.to_thread(
                    parse_html, file_url, html, "", library_name, version
                )
                if parsed:
                    results.append(parsed)
                continue
            else:
                # Handle markdown, rst, txt, mdx files
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
                content, metadata = remove_front_matter(raw_content)

            # Use title from metadata if available, otherwise filename
            title = metadata.get("title")
            if not title:
                title = file_path.stem.replace("-", " ").replace("_", " ").title()

            # Generate description
            description = metadata.get("description")
            if not description:
                if base_path is not None:
                    try:
                        relative_path = file_path.relative_to(base_path)
                        description = f"Documentation file from {relative_path}"
                    except ValueError:
                        description = default_description
                else:
                    description = default_description

            results.append(
                ParsedPage(
                    url=file_url,
                    library_name=library_name,
                    version=version,
                    title=title,
                    description=description,
                    last_modified=None,
                    content=content,
                )
            )
        except Exception as e:
            print(f"Warning: Could not process {file_path}: {e}")

    return results


async def save_results(results: list[ParsedPage], output_dir: Path):
    """
    Save the results to a file.

    Args:
        results: The list of parsed pages to save
        output_dir: The raw data directory for the library/version
    """

    if output_dir.exists():
        print(f"Clearing existing raw data files in {output_dir}...")
        for item in output_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    output_dir.mkdir(parents=True, exist_ok=True)

    valid_results = [r for r in results if r is not None]

    for result in tqdm(
        valid_results, desc="Writing structured raw data files", unit="file"
    ):
        slug = urlparse(result["url"]).path.strip("/").replace("/", "-") or "home"
        file_name = output_dir / f"{slug}.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)


def load_page_hashes_from_directory(directory: Path) -> dict[str, str]:
    """
    Load pages and compute hashes without full ParsedPage objects.

    Args:
        directory: Directory containing JSON page files

    Returns:
        Dictionary mapping URLs to content hashes
    """
    import hashlib

    hashes: dict[str, str] = {}
    if not directory.exists():
        return hashes

    for json_file in directory.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                url = data.get("url")
                content = data.get("content", "")
                if url:
                    hashes[url] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        except (json.JSONDecodeError, KeyError):
            # Skip corrupted files
            continue

    return hashes


def update_raw_data_directory(
    raw_data_dir: Path,
    new_pages: list[ParsedPage],
    modified_pages: list[tuple[str, ParsedPage]],
    deleted_urls: list[str],
) -> None:
    """
    Update raw data folder - replace/add new, delete removed.

    Args:
        raw_data_dir: Path to raw data directory
        new_pages: List of new pages to add
        modified_pages: List of (url, page) tuples for modified pages
        deleted_urls: List of URLs to delete
    """
    # Delete JSON files for deleted_urls
    for url in deleted_urls:
        slug = urlparse(url).path.strip("/").replace("/", "-") or "home"
        file_name = raw_data_dir / f"{slug}.json"
        if file_name.exists():
            file_name.unlink()

    # Save new and modified pages
    pages_to_save = new_pages + [page for _, page in modified_pages]
    for page in tqdm(pages_to_save, desc="Updating raw data files", unit="file"):
        slug = urlparse(page["url"]).path.strip("/").replace("/", "-") or "home"
        file_name = raw_data_dir / f"{slug}.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(page, f, indent=2)
