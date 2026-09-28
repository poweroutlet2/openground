"""
Tests for the raw data file naming logic in openground.extract.common.

The slug is used as a real file name on disk, so it has to be unique (never
overwrite a sibling page), safe on Windows and short enough for MAX_PATH.
"""

import json
from pathlib import Path

import pytest

from openground.extract.common import (
    MAX_PATH_LIMIT,
    ParsedPage,
    build_file_slug,
    save_results,
    slug_length_budget,
)


def make_page(url: str) -> ParsedPage:
    return ParsedPage(
        url=url,
        library_name="testlib",
        version="latest",
        title="Title",
        description=None,
        last_modified="",
        content="content",
    )


def test_forward_slashes_become_hyphens():
    assert build_file_slug("https://example.com/docs/guide/intro") == (
        "docs-guide-intro"
    )


def test_backslashes_become_hyphens():
    """A Windows style path must not leak separators into the file name."""
    slug = build_file_slug(r"file:///C:/Users/dev/docs\guide\intro.md")

    assert "\\" not in slug
    assert "/" not in slug
    assert "-" in slug


def test_empty_path_falls_back_to_home():
    assert build_file_slug("file://") == "home"
    assert build_file_slug("") == "home"
    assert build_file_slug("https://example.com/") == "home"


def test_illegal_characters_are_removed():
    slug = build_file_slug("https://example.com/a<b>c:d*e?f|g")

    for char in '<>:"\\|?*':
        assert char not in slug


def test_reserved_windows_names_are_escaped():
    """NUL.json is still the reserved device NUL on Windows."""
    for name in ["NUL", "con", "COM1", "LPT9"]:
        slug = build_file_slug(f"https://example.com/{name}")
        assert not slug.split(".")[0].upper() in {"NUL", "CON", "COM1", "LPT9"}
        assert slug.startswith("_")


def test_trailing_dots_and_spaces_are_stripped():
    """Windows silently drops these, which could merge two distinct slugs."""
    assert build_file_slug("https://example.com/page.  ") == "page"
    assert not build_file_slug("https://example.com/page...").endswith(".")


def test_short_slug_is_not_truncated():
    slug = build_file_slug("https://example.com/docs/intro", max_length=120)

    assert slug == "docs-intro"


def test_long_slug_respects_max_length():
    long_url = "https://example.com/" + "/".join(f"segment{i}" for i in range(200))
    slug = build_file_slug(long_url, max_length=60)

    assert len(slug) <= 60


def test_truncated_slugs_stay_unique():
    """Two long URLs sharing a prefix must not collapse onto one file.

    This is the data loss case: naive truncation made both pages write to the
    same path and the second silently overwrote the first.
    """
    prefix = "https://example.com/" + "/".join(f"seg{i}" for i in range(80))
    slug_a = build_file_slug(f"{prefix}/alpha", max_length=60)
    slug_b = build_file_slug(f"{prefix}/beta", max_length=60)

    assert slug_a != slug_b
    assert len(slug_a) <= 60
    assert len(slug_b) <= 60


def test_slug_length_budget_shrinks_with_output_dir():
    short = slug_length_budget(Path("C:/raw"))
    long = slug_length_budget(Path("C:/" + "x" * 200))

    assert short > long
    assert long >= 32


@pytest.mark.asyncio
async def test_save_results_keeps_every_page(tmp_path):
    """Distinct pages must produce distinct files, with nothing overwritten."""
    urls = [
        "https://example.com/docs/intro",
        "https://example.com/docs/guide",
        "https://example.com/docs/reference",
    ]
    out = tmp_path / "raw"

    await save_results([make_page(u) for u in urls], out)

    written = sorted(p.name for p in out.glob("*.json"))
    assert len(written) == 3, f"pages were lost: {written}"


@pytest.mark.asyncio
async def test_save_results_bounds_path_length(tmp_path):
    """A very long page path must still produce a writable file name.

    The slug comes from the page URL, which for local sources is the absolute
    file path. A long one would otherwise push the resulting file past the 260
    character MAX_PATH limit of Windows.
    """
    out = tmp_path / "raw"
    # Far longer than any plausible output directory.
    urls = [f"https://example.com/{'segment-' * 60}page{i}" for i in range(5)]

    await save_results([make_page(u) for u in urls], out)

    written = list(out.glob("*.json"))
    assert len(written) == 5, f"pages were lost: {[p.name for p in written]}"

    for path in written:
        full_length = len(str(path.resolve()))
        assert full_length <= MAX_PATH_LIMIT, f"path too long: {full_length}"
        # The digest suffix must keep the truncated names distinct.
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["url"] in urls


@pytest.mark.asyncio
async def test_save_results_bounds_path_in_deep_output_dir(tmp_path):
    """A deep output directory must leave room for the file name."""
    out = tmp_path / ("lib" * 10) / "local-2026-01-01"
    out.mkdir(parents=True)
    urls = [f"https://example.com/{'segment-' * 40}page{i}" for i in range(3)]

    await save_results([make_page(u) for u in urls], out)

    written = list(out.glob("*.json"))
    assert len(written) == 3, f"pages were lost: {[p.name for p in written]}"
    for path in written:
        assert len(str(path.resolve())) <= MAX_PATH_LIMIT


@pytest.mark.asyncio
async def test_local_path_extraction_keeps_every_file(tmp_path):
    """Regression: every local document must yield its own JSON file.

    The local extractor used to build "file://{absolute_path}", a malformed URL
    on Windows. urlparse could not read it, so each page fell back to the
    "home" slug and they all overwrote one another.
    """
    from openground.extract.local_path import extract_local_path

    docs = tmp_path / "docs"
    (docs / "nested").mkdir(parents=True)
    for name in ["README.md", "api.md", "guide.md", "nested/deep.md"]:
        (docs / name).write_text(
            f"# {name}\n\nDocumentation content for the test.", encoding="utf-8"
        )

    out = tmp_path / "out"
    await extract_local_path(
        local_path=docs, output_dir=out, library_name="testlib", version="latest"
    )

    written = list(out.glob("*.json"))
    assert len(written) == 4, f"documents were lost: {[p.name for p in written]}"

    stored = {json.loads(p.read_text(encoding="utf-8"))["url"] for p in written}
    assert len(stored) == 4, "two documents share the same stored URL"
