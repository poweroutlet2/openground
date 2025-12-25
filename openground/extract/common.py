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
        results: The list of parsed pages to save.
        output_dir: The raw data directory for the library.
    """

    if output_dir.exists():
        print("Clearing existing raw data files for library...")
        # Clear existing contents for a clean replacement
        for item in output_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    output_dir.mkdir(parents=True, exist_ok=True)

    valid_results = [r for r in results if r is not None]

    for result in tqdm(
        valid_results, desc="Writing structured raw data files:", unit="file"
    ):
        slug = urlparse(result["url"]).path.strip("/").replace("/", "-") or "home"
        file_name = output_dir / f"{slug}.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
