from typing import TypedDict
from pathlib import Path
import shutil
import json
from urllib.parse import urlparse
from tqdm import tqdm


class ParsedPage(TypedDict):
    url: str
    library_name: str
    version: str
    title: str | None
    description: str | None
    last_modified: str | None
    content: str


async def save_results(results: list[ParsedPage | None], output_dir: Path):
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
