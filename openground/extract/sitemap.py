import asyncio
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import aiohttp

from aiohttp import ClientSession, ClientTimeout
from xml.etree import ElementTree as ET
from tqdm.asyncio import tqdm as async_tqdm

from openground.config import (
    CONCURRENCY_LIMIT,
    DEFAULT_LIBRARY_NAME,
    SITEMAP_URL,
    get_library_raw_data_dir,
)
from openground.console import success

import trafilatura

from openground.extract.common import ParsedPage, save_results


async def fetch_sitemap_urls(
    session: ClientSession,
    url: str,
    filter_keywords: list[str],
) -> set[str]:
    print(f"Getting sitemap: {url}")

    async with session.get(url) as response:
        content = await response.text()

    root = ET.fromstring(content)
    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls = {
        loc.text
        for loc in root.findall(path=".//ns:loc", namespaces=namespace)
        if loc.text
    }
    print(f"Found {len(urls)} unique URLs in sitemap")
    keywords = [k.lower() for k in filter_keywords]
    if keywords:
        urls = {u for u in urls if any(k in u.lower() for k in keywords)}
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
            else:
                # If 404 or other non-200 status, parse an empty robots.txt
                # An empty robots.txt allows all URLs
                rp.parse([])
    except Exception as e:
        print(f"Warning: Could not fetch robots.txt: {e}")
        # Parse empty robots.txt to allow all URLs
        rp.parse([])

    return rp


def filter_urls_by_robots(
    urls: set[str], robot_parser: RobotFileParser, user_agent: str = "*"
) -> set[str]:
    """Filter URLs that are allowed by robots.txt."""
    allowed = {url for url in urls if robot_parser.can_fetch(user_agent, url)}
    return allowed


async def process_url(
    semaphore: asyncio.Semaphore,
    session: ClientSession,
    url: str,
    library_name: str,
    version: str,
) -> ParsedPage | None:
    """
    Process a single URL.

    Args:
        semaphore: The semaphore to use to limit the number of concurrent requests.
        session: The session to use to make the request.
        url: The URL to process.
        library_name: The name of the library/framework for this documentation.
        version: The version string to store in the parsed page.
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
                    parse_html, url, html, last_modified, library_name, version
                )

                return result
        except Exception as e:
            print(f"Error processing URL: {url} - {e}")
            return None


def parse_html(
    url: str, html: str, last_modified: str, library_name: str, version: str
) -> ParsedPage | None:
    """
    Parse the HTML of a page.

    Args:
        url: The URL of the page.
        html: The HTML of the page.
        last_modified: The Last-Modified header value.
        library_name: The name of the library/framework for this documentation.
        version: The version string to store in the parsed page.
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
        version=version,
        title=metadata.title if metadata else "Unknown",
        description=metadata.description,
        last_modified=last_modified,
        content=content,
    )


async def extract_pages(
    sitemap_url: str = SITEMAP_URL,
    concurrency_limit: int = CONCURRENCY_LIMIT,
    library_name: str = DEFAULT_LIBRARY_NAME,
    output_dir: Path | None = None,
    filter_keywords: list[str] = [],
    version: str = "latest",
    trim_query_params: bool = False,
) -> None:
    if output_dir is None:
        output_dir = get_library_raw_data_dir(library_name, version=version)
    connector = aiohttp.TCPConnector()

    async with aiohttp.ClientSession(connector=connector) as session:
        urls = await fetch_sitemap_urls(session, sitemap_url, filter_keywords)

        if trim_query_params:
            original_count = len(urls)
            # Trim query parameters and deduplicate using a set comprehension
            urls = {
                f"{p.scheme}://{p.netloc}{p.path}"
                for url in urls
                if (p := urlparse(url))
            }
            if len(urls) < original_count:
                print(
                    f"Trimmed query parameters: {original_count} -> {len(urls)} unique URLs"
                )

        # Filter by robots.txt
        parsed = urlparse(sitemap_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        robot_parser = await fetch_robots_txt(session, base_url)

        urls = filter_urls_by_robots(urls, robot_parser)
        print(f"Filtered to {len(urls)} URLs after robots.txt check")

        semaphore = asyncio.Semaphore(concurrency_limit)

        tasks = [
            process_url(semaphore, session, url, library_name, version) for url in urls
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
