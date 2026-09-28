"""
Tests for the sitemap extraction pipeline.

These tests spin up a real aiohttp web server on localhost so the actual
ClientSession code path (status codes, Retry-After header, connection reuse)
is exercised end to end instead of being mocked away.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

import pytest
from aiohttp import web

from openground.extract.sitemap import extract_pages

MAX_CONCURRENT_REQUESTS = 5

# Request pacing is disabled in the tests that are not about timing, so the
# suite stays fast. It has its own dedicated tests below.
NO_PACING = 0

PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Doc Page</title>
  <meta name="description" content="A test documentation page">
</head>
<body>
  <article>
    <h1>Heading</h1>
    <p>This is a paragraph with enough text content for the extraction library
    to work properly and return a non-empty result. It needs to be reasonably
    long so that trafilatura does not discard it as boilerplate or noise.</p>
    <p>More content here to ensure extraction succeeds with a decent amount of
    text so the heuristics pass the extraction threshold comfortably.</p>
  </article>
</body>
</html>"""


class ServerProbe:
    """Tracks concurrency and per-URL attempts against a live test server."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0
        self.attempts: dict[str, int] = {}
        self.retry_after = "0.05"
        self._lock = asyncio.Lock()

    async def enter(self) -> int:
        async with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            return self.in_flight

    async def leave(self) -> None:
        async with self._lock:
            self.in_flight -= 1

    async def record(self, url: str) -> int:
        async with self._lock:
            self.attempts[url] = self.attempts.get(url, 0) + 1
            return self.attempts[url]


def build_app(probe: ServerProbe, page_status, path: str = "/page") -> web.Application:
    """Create a test app. `page_status(probe, attempt) -> web.Response`."""

    async def sitemap(request: web.Request) -> web.Response:
        count = int(request.query.get("n", "12"))
        base = f"http://{request.host}"
        body = ['<?xml version="1.0" encoding="UTF-8"?>']
        body.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for i in range(count):
            body.append(f"  <url><loc>{base}{path}{i}</loc></url>")
        body.append("</urlset>")
        return web.Response(text="\n".join(body), content_type="application/xml")

    async def robots(request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

    async def page(request: web.Request) -> web.Response:
        current = await probe.enter()
        try:
            attempt = await probe.record(request.path)
            await asyncio.sleep(0.02)  # simulate server work
            return page_status(probe, attempt, current)
        finally:
            await probe.leave()

    app = web.Application()
    app.router.add_get("/sitemap.xml", sitemap)
    app.router.add_get("/robots.txt", robots)
    app.router.add_get(f"{path}{{i}}", page)
    return app


async def start_server(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = next(iter(runner.addresses))[1]
    return runner, f"http://127.0.0.1:{port}"


def count_saved(output_dir) -> int:
    return len(list(Path(output_dir).glob("*.json")))


def always_ok(probe, attempt, current):
    if current > MAX_CONCURRENT_REQUESTS:
        return web.Response(
            status=429, headers={"Retry-After": probe.retry_after}, text="Too Many"
        )
    return web.Response(text=PAGE_HTML, content_type="text/html")


@pytest.mark.asyncio
async def test_concurrency_never_exceeds_limit_and_no_page_is_lost(tmp_path):
    """A rate-limiting server must not cause dropped pages."""
    probe = ServerProbe()
    app = build_app(probe, always_ok)
    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await extract_pages(
            sitemap_url=f"{base}/sitemap.xml?n=40",
            concurrency_limit=MAX_CONCURRENT_REQUESTS,
            library_name="testlib",
            output_dir=out,
            version="latest",
            request_min_interval=NO_PACING,
        )
    finally:
        await runner.cleanup()

    assert probe.max_in_flight <= MAX_CONCURRENT_REQUESTS, (
        f"exceeded concurrency limit: {probe.max_in_flight}"
    )
    assert count_saved(out) == 40, f"lost pages: {count_saved(out)}/40"


@pytest.mark.asyncio
async def test_recovers_from_429_using_retry_after(tmp_path):
    """Pages answering 429 first must still be extracted after a wait."""

    def throttled(probe, attempt, current):
        if attempt <= 2:
            return web.Response(
                status=429, headers={"Retry-After": probe.retry_after}, text="Slow down"
            )
        return web.Response(text=PAGE_HTML, content_type="text/html")

    probe = ServerProbe()
    app = build_app(probe, throttled)
    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await extract_pages(
            sitemap_url=f"{base}/sitemap.xml?n=10",
            concurrency_limit=MAX_CONCURRENT_REQUESTS,
            library_name="testlib",
            output_dir=out,
            version="latest",
            request_min_interval=NO_PACING,
        )
    finally:
        await runner.cleanup()

    assert count_saved(out) == 10, f"lost pages after 429: {count_saved(out)}/10"


@pytest.mark.asyncio
async def test_recovers_from_transient_5xx(tmp_path):
    """Transient server errors must be retried instead of dropping the page."""

    def flaky(probe, attempt, current):
        if attempt == 1:
            return web.Response(status=503, text="Service Unavailable")
        return web.Response(text=PAGE_HTML, content_type="text/html")

    probe = ServerProbe()
    app = build_app(probe, flaky)
    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await extract_pages(
            sitemap_url=f"{base}/sitemap.xml?n=10",
            concurrency_limit=MAX_CONCURRENT_REQUESTS,
            library_name="testlib",
            output_dir=out,
            version="latest",
            request_min_interval=NO_PACING,
        )
    finally:
        await runner.cleanup()

    assert count_saved(out) == 10, f"lost pages after 503: {count_saved(out)}/10"


@pytest.mark.asyncio
async def test_gives_up_on_permanent_failure(tmp_path):
    """A permanently failing URL must be skipped without hanging forever."""

    def always_429(probe, attempt, current):
        return web.Response(
            status=429, headers={"Retry-After": probe.retry_after}, text="Blocked"
        )

    probe = ServerProbe()
    app = build_app(probe, always_429)
    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await asyncio.wait_for(
            extract_pages(
                sitemap_url=f"{base}/sitemap.xml?n=4",
                concurrency_limit=MAX_CONCURRENT_REQUESTS,
                library_name="testlib",
                output_dir=out,
                version="latest",
                request_min_interval=NO_PACING,
            ),
            timeout=60,
        )
    finally:
        await runner.cleanup()

    assert count_saved(out) == 0
    # Bounded number of attempts: it must not retry forever.
    assert all(count <= 6 for count in probe.attempts.values()), probe.attempts


@pytest.mark.asyncio
async def test_default_concurrency_limit_is_five():
    """The shipped default must be the polite value, not 50."""
    from openground.config import CONCURRENCY_LIMIT

    assert CONCURRENCY_LIMIT == 5


@pytest.mark.asyncio
async def test_stale_config_value_is_clamped(tmp_path):
    """A config file still carrying concurrency_limit=50 must be clamped.

    `openground config` persists the defaults on first run, so existing installs
    keep the old value on disk. Without the ceiling the fix would only reach
    fresh installs and those users would keep getting rate limited.
    """
    probe = ServerProbe()
    app = build_app(probe, always_ok)
    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await extract_pages(
            sitemap_url=f"{base}/sitemap.xml?n=30",
            concurrency_limit=50,  # stale value from an old config file
            library_name="testlib",
            output_dir=out,
            version="latest",
            request_min_interval=NO_PACING,
        )
    finally:
        await runner.cleanup()

    assert probe.max_in_flight <= MAX_CONCURRENT_REQUESTS, (
        f"stale concurrency not clamped: {probe.max_in_flight}"
    )
    assert count_saved(out) == 30


@pytest.mark.asyncio
async def test_lower_user_concurrency_is_honoured(tmp_path):
    """A user asking for fewer than the ceiling must still be obeyed."""
    probe = ServerProbe()
    app = build_app(probe, always_ok)
    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await extract_pages(
            sitemap_url=f"{base}/sitemap.xml?n=12",
            concurrency_limit=2,
            library_name="testlib",
            output_dir=out,
            version="latest",
            request_min_interval=NO_PACING,
        )
    finally:
        await runner.cleanup()

    assert probe.max_in_flight <= 2, f"user limit ignored: {probe.max_in_flight}"
    assert count_saved(out) == 12


@pytest.mark.asyncio
async def test_extraction_config_exposes_retry_knobs():
    """The new knobs must be present in the default config so users can tune."""
    from openground.config import get_default_config

    extraction = get_default_config()["extraction"]

    assert extraction["concurrency_limit"] == 5
    assert extraction["request_timeout"] == 30
    assert extraction["max_retries"] == 3
    assert extraction["retry_backoff_base"] == 1.0
    assert extraction["retry_backoff_max"] == 30.0
    assert extraction["request_min_interval"] == 0.2
    assert "openground" in extraction["user_agent"]


@pytest.mark.asyncio
async def test_requests_are_spaced_by_the_rate_limiter(tmp_path):
    """Request starts must be kept at least `request_min_interval` apart."""
    starts: list[float] = []
    interval = 0.1
    pages = 8

    async def sitemap(request: web.Request) -> web.Response:
        host = f"http://{request.host}"
        locs = "".join(f"<url><loc>{host}/page{i}</loc></url>" for i in range(pages))
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{locs}</urlset>"
        )
        return web.Response(text=body, content_type="application/xml")

    async def robots(request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

    async def page(request: web.Request) -> web.Response:
        starts.append(time.monotonic())
        return web.Response(text=PAGE_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/sitemap.xml", sitemap)
    app.router.add_get("/robots.txt", robots)
    app.router.add_get("/page{i}", page)

    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await asyncio.wait_for(
            extract_pages(
                sitemap_url=f"{base}/sitemap.xml",
                concurrency_limit=MAX_CONCURRENT_REQUESTS,
                library_name="testlib",
                output_dir=out,
                version="latest",
                request_min_interval=interval,
            ),
            timeout=30,
        )
    finally:
        await runner.cleanup()

    assert len(starts) == pages
    starts.sort()
    gaps = [b - a for a, b in pairwise(starts)]
    smallest = min(gaps)

    # 20% tolerance: asyncio timers are not exact, and a slow machine may round
    # in the client's favour, but a burst would collapse the gap to ~0.
    assert smallest >= interval * 0.8, (
        f"requests were not spaced: smallest gap {smallest:.3f}s < {interval}s"
    )


@pytest.mark.asyncio
async def test_rate_limiter_zero_disables_pacing():
    """A zero interval must not add any artificial delay."""
    from openground.extract.sitemap import RateLimiter

    limiter = RateLimiter(0)
    assert limiter.min_interval == 0.0

    started = time.monotonic()
    for _ in range(50):
        await limiter.wait()
    assert time.monotonic() - started < 0.1


@pytest.mark.asyncio
async def test_rate_limiter_reserves_slots_in_order():
    """Concurrent waiters must be released one interval apart, in any order."""
    from openground.extract.sitemap import RateLimiter

    limiter = RateLimiter(0.05)
    order: list[int] = []

    async def worker(index: int) -> None:
        await limiter.wait()
        order.append(index)

    started = time.monotonic()
    await asyncio.gather(*[worker(i) for i in range(5)])
    elapsed = time.monotonic() - started

    # Every worker got its own slot, so the whole batch spans the intervals.
    assert len(order) == 5
    assert elapsed >= 0.05 * 4 * 0.8, f"slots were not reserved: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_backoff_does_not_hold_a_semaphore_slot(tmp_path):
    """A throttled URL must not block the other slots while it waits.

    Both pages are throttled once with a 1s Retry-After and there is only a
    single slot:

    * Releasing the slot while waiting lets both pages sleep concurrently, so
      the run finishes in about 1s.
    * Holding the slot across the sleep forces the pages to wait in sequence,
      so the run takes about 2s.

    The assertion therefore does not depend on which page grabs the slot first.
    """
    attempts: dict[str, int] = {}

    async def sitemap(request: web.Request) -> web.Response:
        host = f"http://{request.host}"
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{host}/page0</loc></url>"
            f"<url><loc>{host}/page1</loc></url>"
            "</urlset>"
        )
        return web.Response(text=body, content_type="application/xml")

    async def robots(request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

    async def page(request: web.Request) -> web.Response:
        path = request.path
        attempts[path] = attempts.get(path, 0) + 1
        if attempts[path] == 1:
            return web.Response(
                status=429, headers={"Retry-After": "1"}, text="Slow down"
            )
        return web.Response(text=PAGE_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/sitemap.xml", sitemap)
    app.router.add_get("/robots.txt", robots)
    app.router.add_get("/page0", page)
    app.router.add_get("/page1", page)

    runner, base = await start_server(app)
    out = tmp_path / "raw"
    started = time.monotonic()
    try:
        await asyncio.wait_for(
            extract_pages(
                sitemap_url=f"{base}/sitemap.xml",
                concurrency_limit=1,
                library_name="testlib",
                output_dir=out,
                version="latest",
                request_min_interval=NO_PACING,
            ),
            timeout=30,
        )
        elapsed = time.monotonic() - started
    finally:
        await runner.cleanup()

    assert count_saved(out) == 2
    assert attempts == {"/page0": 2, "/page1": 2}, attempts
    # ~1s when the waits overlap, ~2s when the slot is held across the sleep.
    assert elapsed < 1.6, f"throttled pages were serialized ({elapsed:.2f}s)"


def test_parse_retry_after_seconds_form():
    from openground.extract.sitemap import parse_retry_after

    assert parse_retry_after("5") == 5.0
    assert parse_retry_after(" 2.5 ") == 2.5
    assert parse_retry_after("0") == 0.0


def test_parse_retry_after_missing_or_garbage():
    from openground.extract.sitemap import parse_retry_after

    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("not-a-date") is None


def test_parse_retry_after_http_date_form():
    from email.utils import format_datetime

    from openground.extract.sitemap import parse_retry_after

    when = datetime.now(timezone.utc) + timedelta(seconds=30)
    delay = parse_retry_after(format_datetime(when))
    assert delay is not None
    assert 25 <= delay <= 31


def test_parse_retry_after_http_date_in_the_past_is_zero():
    from email.utils import format_datetime

    from openground.extract.sitemap import parse_retry_after

    when = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert parse_retry_after(format_datetime(when)) == 0.0


def test_parse_retry_after_is_capped():
    """A hostile or mistaken header must not stall the whole extraction."""
    from openground.extract.sitemap import parse_retry_after

    assert parse_retry_after("99999", cap=30) == 30


def test_backoff_delay_grows_and_stays_within_cap():
    from openground.extract.sitemap import backoff_delay

    firsts = [backoff_delay(1) for _ in range(50)]
    thirds = [backoff_delay(3) for _ in range(50)]
    capped = [backoff_delay(20) for _ in range(50)]

    # Exponential growth between attempts.
    assert min(thirds) > min(firsts)
    # Jitter keeps a spread so retries do not re-synchronize.
    assert len(set(firsts)) > 1
    # Never exceeds the cap.
    assert max(capped) <= 30


@pytest.mark.asyncio
async def test_transport_error_is_retried(tmp_path):
    """A dropped connection must be retried instead of losing the page."""
    attempts = {"n": 0}

    async def sitemap(request: web.Request) -> web.Response:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>http://{request.host}/page0</loc></url>"
            "</urlset>"
        )
        return web.Response(text=body, content_type="application/xml")

    async def robots(request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

    async def page(request: web.Request) -> web.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            # Abruptly drop the connection so the client sees a transport error.
            request.transport.abort()
            return web.Response()
        return web.Response(text=PAGE_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get("/sitemap.xml", sitemap)
    app.router.add_get("/robots.txt", robots)
    app.router.add_get("/page0", page)

    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await asyncio.wait_for(
            extract_pages(
                sitemap_url=f"{base}/sitemap.xml",
                concurrency_limit=MAX_CONCURRENT_REQUESTS,
                library_name="testlib",
                output_dir=out,
                version="latest",
                request_min_interval=NO_PACING,
            ),
            timeout=30,
        )
    finally:
        await runner.cleanup()

    assert attempts["n"] >= 2, "the dropped connection was never retried"
    assert count_saved(out) == 1, "page lost after a transport error"


@pytest.mark.asyncio
async def test_permanent_404_is_skipped_without_retrying(tmp_path):
    """A 404 will never succeed, so it must not consume the retry budget."""
    attempts = {"n": 0}

    async def sitemap(request: web.Request) -> web.Response:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>http://{request.host}/page0</loc></url>"
            "</urlset>"
        )
        return web.Response(text=body, content_type="application/xml")

    async def robots(request: web.Request) -> web.Response:
        return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

    async def page(request: web.Request) -> web.Response:
        attempts["n"] += 1
        return web.Response(status=404, text="Not Found")

    app = web.Application()
    app.router.add_get("/sitemap.xml", sitemap)
    app.router.add_get("/robots.txt", robots)
    app.router.add_get("/page0", page)

    runner, base = await start_server(app)
    out = tmp_path / "raw"
    try:
        await asyncio.wait_for(
            extract_pages(
                sitemap_url=f"{base}/sitemap.xml",
                concurrency_limit=MAX_CONCURRENT_REQUESTS,
                library_name="testlib",
                output_dir=out,
                version="latest",
                request_min_interval=NO_PACING,
            ),
            timeout=10,
        )
    finally:
        await runner.cleanup()

    assert attempts["n"] == 1, "a 404 was retried"
    assert count_saved(out) == 0
