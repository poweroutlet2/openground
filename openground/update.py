from typing import TypedDict
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from tqdm import tqdm

from openground.extract.common import ParsedPage
from openground.query import delete_urls
from openground.config import DEFAULT_DB_PATH, DEFAULT_TABLE_NAME


class PageDiff(TypedDict):
    new: list[ParsedPage]
    deleted: list[str]
    modified: list[tuple[str, ParsedPage]]
    unchanged: list[str]


class UpdateSummary(TypedDict):
    added: int
    deleted: int
    modified: int
    unchanged: int


def compute_content_hash(content: str) -> str:
    """
    Compute SHA-256 hash of content.

    Args:
        content: The content string to hash

    Returns:
        Hexadecimal SHA-256 hash
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_existing_pages_hashes(raw_data_dir: Path) -> dict[str, str]:
    """
    Load existing pages and return {url: hash} dict.

    Only reads url and content fields for efficiency.

    Args:
        raw_data_dir: Directory containing JSON page files

    Returns:
        Dictionary mapping URLs to content hashes
    """
    hashes: dict[str, str] = {}
    if not raw_data_dir.exists():
        return hashes

    for json_file in raw_data_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                url = data.get("url")
                content = data.get("content", "")
                if url:
                    hashes[url] = compute_content_hash(content)
        except (json.JSONDecodeError, KeyError):
            continue

    return hashes


def compare_pages(
    extracted_pages: list[ParsedPage], existing_hashes: dict[str, str]
) -> PageDiff:
    """
    Compare extracted pages with existing and return diff.

    Args:
        extracted_pages: List of newly extracted pages
        existing_hashes: Dict of {url: hash} from existing data

    Returns:
        PageDiff with new, deleted, modified, and unchanged pages
    """
    extracted_dict: dict[str, ParsedPage] = {
        page["url"]: page for page in extracted_pages
    }
    extracted_urls = set(extracted_dict.keys())
    existing_urls = set(existing_hashes.keys())

    new_urls = extracted_urls - existing_urls
    deleted_urls = existing_urls - extracted_urls
    common_urls = extracted_urls & existing_urls

    new_pages = [extracted_dict[url] for url in new_urls]

    modified: list[tuple[str, ParsedPage]] = []
    unchanged: list[str] = []

    for url in common_urls:
        page = extracted_dict[url]
        existing_hash = existing_hashes[url]
        new_hash = compute_content_hash(page["content"])
        if existing_hash != new_hash:
            modified.append((url, page))
        else:
            unchanged.append(url)

    return PageDiff(
        new=new_pages,
        deleted=sorted(deleted_urls),
        modified=modified,
        unchanged=unchanged,
    )


def perform_update(
    extracted_pages: list[ParsedPage],
    library_name: str,
    version: str,
    raw_data_dir: Path,
    db_path: Path = DEFAULT_DB_PATH,
    table_name: str = DEFAULT_TABLE_NAME,
) -> UpdateSummary:
    """
    Perform complete update flow.

    1. Compute diff between extracted and existing pages
    2. Delete LanceDB records for modified+deleted pages
    3. Embed and insert new+modified pages
    4. Update raw data folder to match

    Args:
        extracted_pages: List of newly extracted pages
        library_name: Name of the library
        version: Version string
        db_path: Path to LanceDB database
        table_name: Name of the LanceDB table
        raw_data_dir: Path to raw data directory for this library/version

    Returns:
        UpdateSummary with counts of added, deleted, modified, and unchanged pages
    """
    if not extracted_pages:
        raise ValueError(
            "Extraction produced no pages. Please check your source configuration."
        )

    # Load existing hashes and compute diff
    existing_hashes = load_existing_pages_hashes(raw_data_dir)
    diff = compare_pages(extracted_pages, existing_hashes)

    # Delete LanceDB records for modified and deleted pages
    urls_to_delete = diff["deleted"] + [url for url, _ in diff["modified"]]
    if urls_to_delete:
        batch_size = 1000
        for i in range(0, len(urls_to_delete), batch_size):
            batch = urls_to_delete[i : i + batch_size]
            delete_urls(
                urls=batch,
                library_name=library_name,
                version=version,
                db_path=db_path,
                table_name=table_name,
            )

    # Embed and insert new and modified pages
    pages_to_ingest = diff["new"] + [page for _, page in diff["modified"]]
    if pages_to_ingest:
        from openground.ingest import ingest_pages_to_lancedb

        ingest_pages_to_lancedb(
            pages=pages_to_ingest,
            db_path=db_path,
            table_name=table_name,
        )

    # Update raw data folder
    # Delete JSON files for deleted URLs
    for url in diff["deleted"]:
        slug = urlparse(url).path.strip("/").replace("/", "-") or "home"
        file_name = raw_data_dir / f"{slug}.json"
        if file_name.exists():
            file_name.unlink()

    # Save new and modified pages
    pages_to_save = pages_to_ingest
    for page in tqdm(pages_to_save, desc="Updating raw data files", unit="file"):
        slug = urlparse(page["url"]).path.strip("/").replace("/", "-") or "home"
        file_name = raw_data_dir / f"{slug}.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(page, f, indent=2)

    return UpdateSummary(
        added=len(diff["new"]),
        deleted=len(diff["deleted"]),
        modified=len(diff["modified"]),
        unchanged=len(diff["unchanged"]),
    )
