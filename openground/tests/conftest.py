"""
Global test fixtures for isolated testing.

This module provides fixtures that ensure every test runs in a temporary
sandbox environment, never touching real user data.
"""

import pytest


@pytest.fixture(autouse=True)
def mock_isolated_env(monkeypatch, tmp_path):
    """Point config, data and home at tmp_path so tests never touch real user data."""
    fake_data = tmp_path / "data"
    fake_config = tmp_path / "config"
    fake_data.mkdir(parents=True)
    fake_config.mkdir(parents=True)

    monkeypatch.setenv("XDG_DATA_HOME", str(fake_data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_config))
    # install tests write under the home directory
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    monkeypatch.setattr("openground.config._settings_cache", None)

    return fake_data


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
            content="Content of page 1",
        ),
        ParsedPage(
            url="https://example.com/page2",
            library_name="testlib",
            version="latest",
            title="Page 2",
            description="Second page",
            last_modified="2024-01-02",
            content="Content of page 2",
        ),
        ParsedPage(
            url="https://example.com/page3",
            library_name="testlib",
            version="latest",
            title="Page 3",
            description="Third page",
            last_modified="2024-01-03",
            content="Content of page 3",
        ),
    ]


@pytest.fixture
def fake_embeddings(monkeypatch):
    """Replace the embedding model with constant vectors."""

    def embed(texts, show_progress=True):
        return [[0.1] * 384 for _ in texts]

    monkeypatch.setattr("openground.ingest.generate_embeddings", embed)
    monkeypatch.setattr("openground.query.generate_embeddings", embed)


class FakeSource:
    """Stands in for git/sitemap/local extraction: writes `pages` into the output dir."""

    def __init__(self):
        self.pages: dict[str, str] = {"intro": "Intro page", "guide": "Guide page"}
        self.calls: list[dict] = []
        self.refs: dict[str, str | None] = {}  # git ref aliases; None = missing

    def _write(self, kwargs):
        import json

        out = kwargs["output_dir"]
        out.mkdir(parents=True, exist_ok=True)
        for slug, content in self.pages.items():
            page = {
                "url": f"https://example.com/{slug}",
                "library_name": kwargs["library_name"],
                "version": kwargs["version"],
                "title": slug,
                "description": None,
                "last_modified": None,
                "content": content,
            }
            (out / f"{slug}.json").write_text(json.dumps(page))

    async def extract(self, **kwargs):
        self.calls.append(kwargs)
        self._write(kwargs)


@pytest.fixture
def fake_source(monkeypatch, fake_embeddings):
    source = FakeSource()
    monkeypatch.setattr("openground.extract.git.extract_repo", source.extract)
    monkeypatch.setattr("openground.extract.sitemap.extract_pages", source.extract)
    monkeypatch.setattr(
        "openground.extract.local_path.extract_local_path", source.extract
    )
    monkeypatch.setattr(
        "openground.extract.git.resolve_remote_ref",
        lambda repo_url, version: source.refs.get(version, version),
    )
    return source
