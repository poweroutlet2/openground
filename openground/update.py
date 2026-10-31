from typing import TypedDict
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from tqdm import tqdm

from openground.extract.common import ParsedPage
from openground.query import delete_urls


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
    """SHA-256 hex digest of page content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_existing_pages_hashes(raw_data_dir: Path) -> dict[str, str]:
    """Map each stored page URL to the hash of its content."""
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
    """Split extracted pages into new, modified, unchanged and deleted (by URL)."""
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
) -> UpdateSummary:
    """Diff against stored pages, then re-embed what changed and sync the raw files."""
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
            )

    # Embed and insert new and modified pages
    pages_to_ingest = diff["new"] + [page for _, page in diff["modified"]]
    if pages_to_ingest:
        from openground.ingest import ingest_pages

        ingest_pages(
            pages=pages_to_ingest,
        )

    # Update raw data folder
    raw_data_dir.mkdir(parents=True, exist_ok=True)
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
