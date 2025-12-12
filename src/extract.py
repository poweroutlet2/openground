import asyncio
import json
import os
from typing import TypedDict
from urllib.parse import urlparse
import aiohttp

from aiohttp import ClientSession, ClientTimeout
from xml.etree import ElementTree as ET
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

import trafilatura


class ParsedPage(TypedDict):
    url: str
    collection_title: str
    title: str | None
    description: str | None
    last_modified: str | None
    content: str


SITEMAP_URL = "https://docs.databricks.com/aws/en/sitemap.xml"
CONCURRENCY_LIMIT = 50

COLLECTION_TITLE = "Databricks"
OUTPUT_DIR = f"raw_data/docs/{COLLECTION_TITLE}"
FILTER_KEYWORDS = ["docs", "documentation", "blog"]


async def fetch_sitemap_urls(
    session: ClientSession,
    url: str,
    filter_keywords: list[str],
):
    print(f"Getting sitemap: {url}")

    async with session.get(url) as response:
        content = await response.text()

    root = ET.fromstring(content)
    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = [loc.text for loc in root.findall(path=".//ns:loc", namespaces=namespace)]
    print(f"Found {len(urls)} URLs in sitemap")
    keywords = [k.lower() for k in filter_keywords]
    if keywords:
        urls = [u for u in urls if u and any(k in u.lower() for k in keywords)]
        print(f"Filtered to {len(urls)} URLs after keyword filtering")

    return urls


async def process_url(
    semaphore: asyncio.Semaphore,
    session: ClientSession,
    url: str,
    collection_title: str,
):
    """
    Process a single URL.

    Args:
        semaphore: The semaphore to use to limit the number of concurrent requests.
        session: The session to use to make the request.
        url: The URL to process.
        collection_title: The title of the documentation site.
    """

    async with semaphore:
        try:
            async with session.get(url, timeout=ClientTimeout(total=10)) as response:
                if response.status != 200:
                    print(f"Error: {response.status} {url}")
                    return None

                html = await response.text()
                last_modified = response.headers.get("Last-Modified") or ""

                result = await asyncio.to_thread(
                    parse_html, url, html, last_modified, collection_title
                )

                return result
        except Exception as e:
            print(f"Error processing URL: {url} - {e}")
            return None


def parse_html(url: str, html: str, last_modified: str, collection_title: str):
    """
    Parse the HTML of a page.

    Args:
        html: The HTML of the page.
        collection_title: The title of the documentation site.
    """
    metadata = trafilatura.extract_metadata(html)
    content = trafilatura.extract(
        html,
        include_formatting=True,
        include_links=True,
        include_images=True,
        output_format="markdown",
    )

    if not content:
        return None

    return ParsedPage(
        url=url,
        collection_title=collection_title,
        title=metadata.title if metadata else "Unknown",
        description=metadata.description if metadata else "",
        last_modified=last_modified,
        content=content,
    )


async def save_results(results: list[ParsedPage | None], output_dir: str):
    """
    Save the results to a file.

    Args:
        results: The list of parsed pages to save.
        output_dir: The directory to save the results to.
    """

    os.makedirs(f"{output_dir}", exist_ok=True)

    valid_results = [r for r in results if r is not None]

    for result in tqdm(valid_results, desc="Saving files", unit="file"):
        slug = urlparse(result["url"]).path.strip("/").replace("/", "-") or "home"
        file_name = f"{output_dir}/{slug}.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)


async def main(
    sitemap_url: str = SITEMAP_URL,
    concurrency_limit: int = CONCURRENCY_LIMIT,
    collection_title: str = COLLECTION_TITLE,
    output_dir: str = OUTPUT_DIR,
    filter_keywords: list[str] = FILTER_KEYWORDS,
):
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        urls = await fetch_sitemap_urls(session, sitemap_url, filter_keywords)

        semaphore = asyncio.Semaphore(concurrency_limit)

        tasks = [
            process_url(semaphore, session, url, collection_title)
            for url in urls
            if url is not None
        ]

        # Use tqdm to track async task progress
        pbar = async_tqdm(total=len(tasks), desc="Processing URLs", unit="page")

        async def process_with_progress(task):
            result = await task
            pbar.update(1)
            return result

        results = await asyncio.gather(*[process_with_progress(task) for task in tasks])
        pbar.close()

        await save_results(results, output_dir)
        valid_count = sum(1 for r in results if r is not None)
        print(f"🎉 Saved {valid_count} pages!")


if __name__ == "__main__":
    asyncio.run(main())
