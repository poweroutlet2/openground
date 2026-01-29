"""
Global test fixtures for isolated testing.

This module provides fixtures that ensure every test runs in a temporary
sandbox environment, never touching real user data.
"""
import pytest
import respx
import httpx
from pathlib import Path
from openground.config import clear_config_cache


@pytest.fixture(autouse=True)
def mock_isolated_env(monkeypatch, tmp_path):
    """
    Creates a sandbox for EVERY test.

    This fixture runs automatically before each test function:
    1. Creates a temp dir (tmp_path) unique to this test
    2. Overrides XDG_DATA_HOME and XDG_CONFIG_HOME to point to temp dir
    3. Clears openground's internal config cache
    4. Yields control to the test
    5. Cleans up cache after test (tmp_path auto-deleted by pytest)
    """
    # Create subdirectories for realism
    fake_data = tmp_path / "data"
    fake_config = tmp_path / "config"
    fake_data.mkdir(parents=True)
    fake_config.mkdir(parents=True)

    # Override the environment variables that config.py checks
    monkeypatch.setenv("XDG_DATA_HOME", str(fake_data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_config))

    # CRITICAL: Reset the singleton config cache so app re-reads new paths
    clear_config_cache()

    yield fake_data  # Test runs here

    # Cleanup - clear cache again for safety
    clear_config_cache()


@pytest.fixture
def mock_sitemap_response(respx_mock):
    """
    Mock HTTP responses for sitemap extraction.

    Returns a function that can be used to set up mock sitemap responses.
    """
    def _setup_sitemap(base_url: str, urls: list[str]):
        """Set up mock sitemap.xml with given URLs."""
        sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url in urls:
            sitemap_xml += f'  <url><loc>{url}</loc></url>\n'
        sitemap_xml += '</urlset>'

        respx_mock.get(f"{base_url.rstrip('/')}/sitemap.xml").return_value = httpx.Response(
            200, text=sitemap_xml
        )

        # Also mock each page URL
        for url in urls:
            respx_mock.get(url).return_value = httpx.Response(
                200, text="<html><body>Test content</body></html>"
            )

    return _setup_sitemap


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary path for LanceDB database."""
    return tmp_path / "lancedb"


@pytest.fixture
def temp_raw_data_dir(tmp_path):
    """Create a temporary path for raw data storage."""
    return tmp_path / "raw_data"


@pytest.fixture
def sample_pages():
    """Sample ParsedPage objects for testing."""
    from openground.extract.common import ParsedPage

    return [
        ParsedPage(
            url="https://example.com/page1",
            library_name="testlib",
            version="latest",
            title="Page 1",
            description="First page",
            last_modified="2024-01-01",
            content="Content of page 1"
        ),
        ParsedPage(
            url="https://example.com/page2",
            library_name="testlib",
            version="latest",
            title="Page 2",
            description="Second page",
            last_modified="2024-01-02",
            content="Content of page 2"
        ),
        ParsedPage(
            url="https://example.com/page3",
            library_name="testlib",
            version="latest",
            title="Page 3",
            description="Third page",
            last_modified="2024-01-03",
            content="Content of page 3"
        ),
    ]
