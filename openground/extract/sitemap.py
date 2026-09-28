import asyncio
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    REQUEST_MIN_INTERVAL,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
    SITEMAP_URL,
    USER_AGENT,
    get_library_raw_data_dir,
)

import trafilatura

from openground.extract.common import ParsedPage, save_results

# Status codes worth another attempt: rate limiting, request timeout,
# "Too Early" and the transient family of 5xx server errors.
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Transport level failures that a later attempt may survive.
RETRYABLE_EXCEPTIONS = (
    asyncio.TimeoutError,
    aiohttp.ServerTimeoutError,
    aiohttp.ClientConnectionError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ClientPayloadError,
    aiohttp.TooManyRedirects,
    aiohttp.InvalidURL,
    OSError,
)


def parse_retry_after(
    value: str | None, cap: float = RETRY_BACKOFF_MAX
) -> float | None:
    """
    Convert a ``Retry-After`` header into a delay in seconds.

    Supports both forms allowed by RFC 9110: a plain number of seconds and an
    HTTP-date. The result is always clamped to ``[0, cap]`` so a hostile or
    mistaken header cannot stall the whole extraction.

    Args:
        value: The raw header value, if the server sent one.
        cap: Upper bound in seconds for the returned delay.

    Returns:
        Seconds to wait, or None when the header is missing or unparseable.
    """
    if not value:
        return None

    value = value.strip()

    # Form 1: delay in seconds.
    try:
        return max(0.0, min(float(value), cap))
    except ValueError:
        pass

    # Form 2: HTTP-date.
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    delta = (when - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, min(delta, cap))


def backoff_delay(
    attempt: int,
    base: float = RETRY_BACKOFF_BASE,
    cap: float = RETRY_BACKOFF_MAX,
) -> float:
    """
    Compute an exponential backoff delay with jitter.

    The jitter keeps the retries from re-synchronizing into another burst,
    which is exactly what triggers a second rate limit.

    Args:
        attempt: 1-based number of the attempt that just failed.
        base: Base delay in seconds.
        cap: Upper bound in seconds.

    Returns:
        Seconds to wait before the next attempt.
    """
    delay = min(cap, base * (2 ** (attempt - 1)))
    return delay * (0.5 + random.random() / 2)


class RateLimiter:
    """
    Spaces out the start of requests to keep a polite request rate.

    The semaphore bounds how many requests are in flight, but it does nothing
    to stop the crawler from launching a burst of them. Rate limiting gateways
    measure the arrival rate, so this gate keeps at least ``min_interval``
    seconds between two consecutive request starts.

    A single instance must be shared by every worker of an extraction.
    """

    def __init__(self, min_interval: float = REQUEST_MIN_INTERVAL) -> None:
        """
        Args:
            min_interval: Minimum seconds between two request starts. Values
                of zero or less disable the pacing entirely.
        """
        self.min_interval = max(0.0, min_interval)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        """Block until this request is allowed to start."""
        if self.min_interval <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            delay = self._next_allowed - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            # Reserve the slot for this request before releasing the lock.
            self._next_allowed = now + self.min_interval


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
    rate_limiter: "RateLimiter | None" = None,
) -> ParsedPage | None:
    """
    Process a single URL, retrying transient and throttled failures.

    Rate limited (429) and temporarily unavailable (5xx) responses are retried
    with exponential backoff, honouring the ``Retry-After`` header when the
    server provides one. Permanent failures (404, 403, ...) are skipped right
    away instead of burning the retry budget.

    Args:
        semaphore: The semaphore to use to limit the number of concurrent requests.
        session: The session to use to make the request.
        url: The URL to process.
        library_name: The name of the library/framework for this documentation.
        version: The version string to store in the parsed page.
        rate_limiter: Optional shared gate that spaces out request starts.

    Returns:
        The parsed page, or None when the URL could not be extracted.
    """

    for attempt in range(1, MAX_RETRIES + 2):
        retry_after: float | None = None

        # Paced before taking a concurrency slot, so waiting for the gate never
        # blocks one of the few available slots.
        if rate_limiter is not None:
            await rate_limiter.wait()

        try:
            # The semaphore is held only while the request is in flight, never
            # across the backoff sleep. A throttled URL therefore does not keep
            # one of the limited slots busy while it waits.
            async with (
                semaphore,
                session.get(
                    url, timeout=ClientTimeout(total=REQUEST_TIMEOUT)
                ) as response,
            ):
                if response.status == 200:
                    html = await response.text()
                    last_modified = response.headers.get("Last-Modified") or ""

                    return await asyncio.to_thread(
                        parse_html,
                        url,
                        html,
                        last_modified,
                        library_name,
                        version,
                    )

                if response.status not in RETRYABLE_STATUS_CODES:
                    print(f"Skipping {url}: HTTP {response.status}")
                    return None

                reason = f"HTTP {response.status}"
                retry_after = parse_retry_after(response.headers.get("Retry-After"))

        except RETRYABLE_EXCEPTIONS as exc:
            # Timeouts, dropped connections and truncated payloads.
            reason = f"{type(exc).__name__}: {exc}"
            retry_after = None

        except Exception as exc:  # noqa: BLE001
            # Safety net: a single odd error must never abort the whole run.
            print(f"Error processing URL: {url} - {exc}")
            return None

        if attempt > MAX_RETRIES:
            print(f"Giving up on {url} after {MAX_RETRIES} retries ({reason})")
            return None

        delay = (
            retry_after
            if retry_after is not None
            else backoff_delay(attempt, RETRY_BACKOFF_BASE, RETRY_BACKOFF_MAX)
        )
        print(
            f"Throttled: {url} ({reason}). "
            f"Waiting {delay:.1f}s before retry {attempt}/{MAX_RETRIES}"
        )
        await asyncio.sleep(delay)

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
    request_min_interval: float = REQUEST_MIN_INTERVAL,
) -> None:
    if output_dir is None:
        output_dir = get_library_raw_data_dir(library_name, version=version)

    # Clamp to the politeness ceiling. A config file written before this fix
    # may still carry concurrency_limit=50, which would keep triggering rate
    # limits; lower values chosen by the user are still honoured.
    requested_limit = concurrency_limit
    concurrency_limit = max(1, min(requested_limit, MAX_CONCURRENT_REQUESTS))
    if concurrency_limit != requested_limit:
        print(
            f"Concurrency limited to {concurrency_limit} "
            f"(requested {requested_limit}, max {MAX_CONCURRENT_REQUESTS}) "
            "to avoid rate limiting."
        )

    # Keep the connection pool aligned with the semaphore, otherwise the
    # connector default (100) would allow far more sockets than we intend.
    connector = aiohttp.TCPConnector(limit=concurrency_limit)

    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": USER_AGENT},
    ) as session:
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
        # Shared by every worker so the pacing is global, not per coroutine.
        rate_limiter = RateLimiter(request_min_interval)

        tasks = [
            process_url(semaphore, session, url, library_name, version, rate_limiter)
            for url in urls
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
