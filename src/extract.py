import asyncio
import json
import os
from typing import TypedDict
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import aiohttp

from aiohttp import ClientSession, ClientTimeout
from xml.etree import ElementTree as ET
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

from src.config import (
    CONCURRENCY_LIMIT,
    DEFAULT_LIBRARY_NAME,
    DEFAULT_RAW_DATA_DIR,
    FILTER_KEYWORDS,
    SITEMAP_URL,
)

import trafilatura


class ParsedPage(TypedDict):
    url: str
    library_name: str
    title: str | None
    description: str | None
    last_modified: str | None
    content: str


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


async def fetch_robots_txt(session: ClientSession, base_url: str) -> RobotFileParser:
    """Fetch and parse robots.txt from the base URL."""
    robots_url = f"{base_url}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)

    try:
        async with session.get(robots_url) as response:
            if response.status == 200:
                content = await response.text()
                rp.parse(content.splitlines())
            # If 404 or other error, all URLs are allowed by default
    except Exception as e:
        print(f"Warning: Could not fetch robots.txt: {e}")

    return rp


def filter_urls_by_robots(
    urls: list[str], robot_parser: RobotFileParser, user_agent: str = "*"
) -> list[str]:
    """Filter URLs that are allowed by robots.txt."""
    allowed = [url for url in urls if url and robot_parser.can_fetch(user_agent, url)]
    return allowed


async def process_url(
    semaphore: asyncio.Semaphore,
    session: ClientSession,
    url: str,
    library_name: str,
):
    """
    Process a single URL.

    Args:
        semaphore: The semaphore to use to limit the number of concurrent requests.
        session: The session to use to make the request.
        url: The URL to process.
        library_name: The name of the library/framework for this documentation.
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
                    parse_html, url, html, last_modified, library_name
                )

                return result
        except Exception as e:
            print(f"Error processing URL: {url} - {e}")
            return None


def parse_html(url: str, html: str, last_modified: str, library_name: str):
    """
    Parse the HTML of a page.

    Args:
        html: The HTML of the page.
        library_name: The name of the library/framework for this documentation.
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
        # Heuristic check for JS-required pages
        js_indicators = [
            "BAILOUT_TO_CLIENT_SIDE_RENDERING",
            "_next/static",
            'id="root"',
            'id="app"',
            'id="__next"',
            "You need to enable JavaScript",
        ]
        if any(indicator in html for indicator in js_indicators):
            print(
                f"Warning: Page likely requires JavaScript to render (detected SPA/CSR indicators): {url}"
            )
        else:
            print(f"Warning: No content extracted for {url}")
        return None

    return ParsedPage(
        url=url,
        library_name=library_name,
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
    library_name: str = DEFAULT_LIBRARY_NAME,
    output_dir: str = str(DEFAULT_RAW_DATA_DIR),
    filter_keywords: list[str] = FILTER_KEYWORDS,
):
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        urls = await fetch_sitemap_urls(session, sitemap_url, filter_keywords)

        # Filter by robots.txt
        parsed = urlparse(sitemap_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        robot_parser = await fetch_robots_txt(session, base_url)
        # Filter out None values before robots.txt check
        valid_urls = [url for url in urls if url is not None]
        urls = filter_urls_by_robots(valid_urls, robot_parser)
        print(f"Filtered to {len(urls)} URLs after robots.txt check")

        semaphore = asyncio.Semaphore(concurrency_limit)

        tasks = [
            process_url(semaphore, session, url, library_name)
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
