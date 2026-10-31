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


def page_path(directory: Path, url: str) -> Path:
    """Raw-data JSON file for a page URL."""
    slug = urlparse(url).path.strip("/").replace("/", "-") or "home"
    return directory / f"{slug}.json"


def filter_documentation_files(
    docs_dir: Path, allowed_extensions: set[str] | None = None
) -> list[Path]:
    """Find doc files (README always, minus LICENSE/CHANGELOG/AUTHORS) under docs_dir."""
    if allowed_extensions is None:
        allowed_extensions = {".md", ".rst", ".txt", ".mdx", ".ipynb", ".html", ".htm"}

    doc_files = []

    for root, dirs, files in os.walk(docs_dir):
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
                if file.startswith("."):
                    continue

                if file.upper().startswith("README"):
                    doc_files.append(file_path)
                    continue

                if file not in {
                    "LICENSE",
                    "CHANGELOG",
                    "AUTHORS",
                }:
                    doc_files.append(file_path)

    return doc_files


def extract_notebook_content(file_path: Path) -> tuple[str, dict[str, str]]:
    """Flatten a notebook into markdown text plus title/description metadata."""
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
    """Split YAML front matter off the content, returning (content, metadata)."""
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
    """Parse doc files (md/rst/txt/mdx/ipynb/html) into pages, skipping unreadable ones."""
    from openground.extract.sitemap import parse_html

    results: list[ParsedPage] = []

    for file_path in doc_files:
        try:
            file_url = url_generator(file_path)

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
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
                content, metadata = remove_front_matter(raw_content)

            title = metadata.get("title")
            if not title:
                title = file_path.stem.replace("-", " ").replace("_", " ").title()

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
    """Replace the contents of output_dir with one JSON file per page."""
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
        with open(page_path(output_dir, result["url"]), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
