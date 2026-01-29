"""
Tests for the update feature.
Tests the incremental update logic that compares, syncs, and updates documentation.
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import lancedb

from openground.update import (
    compute_content_hash,
    load_existing_pages_hashes,
    compare_pages,
    perform_update,
    PageDiff,
    UpdateSummary,
)
from openground.extract.common import ParsedPage
from openground.config import get_effective_config


class TestComputeContentHash:
    """Test content hash computation."""

    def test_same_content_same_hash(self):
        # Arrange: Prepare test content
        content = "This is test content"

        # Act: Compute hash twice
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        # Assert: Same content should produce same hash
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        # Arrange: Prepare two different content strings
        content_a = "Content A"
        content_b = "Content B"

        # Act: Compute hashes for both
        hash1 = compute_content_hash(content_a)
        hash2 = compute_content_hash(content_b)

        # Assert: Different content should produce different hashes
        assert hash1 != hash2



class TestLoadExistingPageHashes:
    """Test loading existing page hashes from disk."""

    def test_load_from_nonexistent_directory(self, tmp_path):
        """Should return empty dict for nonexistent directory."""
        # Arrange: Create path to nonexistent directory
        nonexistent_dir = tmp_path / "nonexistent"

        # Act: Try to load hashes from nonexistent directory
        result = load_existing_pages_hashes(nonexistent_dir)

        # Assert: Should return empty dict, not raise error
        assert result == {}

    def test_load_valid_pages(self, temp_raw_data_dir, sample_pages):
        """Should correctly load hashes from valid JSON files."""
        from urllib.parse import urlparse

        # Arrange: Create test library directory and save sample pages
        lib_dir = temp_raw_data_dir / "testlib" / "latest"
        lib_dir.mkdir(parents=True)

        for page in sample_pages:
            # Use same slug logic as update.py
            slug = urlparse(page["url"]).path.strip("/").replace("/", "-") or "home"
            file_path = lib_dir / f"{slug}.json"
            with open(file_path, "w") as f:
                json.dump(page, f)

        # Act: Load hashes from the directory
        hashes = load_existing_pages_hashes(lib_dir)

        # Assert: All sample pages should be loaded
        assert len(hashes) == 3
        assert all(url in hashes for url in [p["url"] for p in sample_pages])

    def test_skips_corrupted_files(self, temp_raw_data_dir):
        """Should gracefully skip corrupted JSON files."""
        # Arrange: Create directory with valid and corrupted files
        lib_dir = temp_raw_data_dir / "testlib" / "latest"
        lib_dir.mkdir(parents=True)

        valid_page = ParsedPage(
            url="https://example.com/valid",
            library_name="testlib",
            version="latest",
            title="Valid",
            description="Valid page",
            last_modified=None,
            content="Valid content"
        )
        with open(lib_dir / "valid.json", "w") as f:
            json.dump(valid_page, f)

        # Create corrupted JSON file
        with open(lib_dir / "corrupted.json", "w") as f:
            f.write("{invalid json")

        # Act: Load hashes (should skip corrupted file)
        hashes = load_existing_pages_hashes(lib_dir)

        # Assert: Only valid file should be loaded
        assert len(hashes) == 1
        assert "https://example.com/valid" in hashes


class TestComparePages:
    """Test page comparison logic."""

    def test_identifies_new_pages(self, sample_pages):
        """Should identify pages not in existing hashes."""
        # Arrange: No existing pages, all extracted pages are new
        existing = {}

        # Act: Compare pages
        diff = compare_pages(sample_pages, existing)

        # Assert: All pages should be marked as new
        assert len(diff["new"]) == 3
        assert len(diff["deleted"]) == 0
        assert len(diff["modified"]) == 0
        assert len(diff["unchanged"]) == 0

    def test_identifies_deleted_pages(self, sample_pages):
        """Should identify URLs in existing but not extracted."""
        # Arrange: Existing page not in extracted set
        existing = {
            "https://example.com/old-page": compute_content_hash("old content")
        }

        # Act: Compare pages
        diff = compare_pages(sample_pages, existing)

        # Assert: Old page should be marked as deleted
        assert len(diff["deleted"]) == 1
        assert "https://example.com/old-page" in diff["deleted"]

    def test_identifies_modified_pages(self, sample_pages):
        """Should identify pages with changed content."""
        # Arrange: Existing pages have different content (different hash)
        existing = {
            page["url"]: compute_content_hash("DIFFERENT content")
            for page in sample_pages
        }

        # Act: Compare pages
        diff = compare_pages(sample_pages, existing)

        # Assert: All pages should be marked as modified
        assert len(diff["modified"]) == 3
        assert len(diff["unchanged"]) == 0

    def test_identifies_unchanged_pages(self, sample_pages):
        """Should identify pages with same content hash."""
        # Arrange: Existing pages have same content (same hash)
        existing = {
            page["url"]: compute_content_hash(page["content"])
            for page in sample_pages
        }

        # Act: Compare pages
        diff = compare_pages(sample_pages, existing)

        # Assert: All pages should be marked as unchanged
        assert len(diff["unchanged"]) == 3
        assert len(diff["modified"]) == 0

    def test_mixed_scenario(self, sample_pages):
        """Test with new, deleted, modified, and unchanged pages."""
        # Arrange: Create a mix of scenarios
        existing = {
            # page1: unchanged (same content)
            sample_pages[0]["url"]: compute_content_hash(sample_pages[0]["content"]),
            # page2: modified (different content)
            sample_pages[1]["url"]: compute_content_hash("OLD content"),
            # deleted page: exists in old but not in extracted
            "https://example.com/deleted": compute_content_hash("deleted content"),
        }
        # Extracted pages: page1 and page3 (page2 removed)
        extracted = [sample_pages[0], sample_pages[2]]

        # Act: Compare pages
        diff = compare_pages(extracted, existing)

        # Assert: Correctly identify each category
        assert len(diff["new"]) == 1  # page3
        assert len(diff["deleted"]) == 2  # page2 + deleted page
        assert len(diff["modified"]) == 0  # page2 is deleted, not modified
        assert len(diff["unchanged"]) == 1  # page1


class TestPerformUpdate:
    """Test the complete update flow."""

    def test_raises_on_empty_extraction(self, temp_raw_data_dir, temp_db_path):
        """Should raise ValueError if extraction produces no pages."""
        # Arrange: Create library directory with existing data
        lib_dir = temp_raw_data_dir / "testlib" / "latest"
        lib_dir.mkdir(parents=True)

        existing_page = ParsedPage(
            url="https://example.com/existing",
            library_name="testlib",
            version="latest",
            title="Existing",
            description="Existing page",
            last_modified=None,
            content="Existing content"
        )
        with open(lib_dir / "existing.json", "w") as f:
            json.dump(existing_page, f)

        # Act & Assert: Should raise ValueError for empty extraction
        with pytest.raises(ValueError, match="produced no pages"):
            perform_update(
                extracted_pages=[],
                library_name="testlib",
                version="latest",
                raw_data_dir=lib_dir,
                db_path=temp_db_path,
                table_name="test_table",
            )

    @patch("openground.ingest.ingest_pages_to_lancedb")
    @patch("openground.update.delete_urls")
    def test_new_library_update(
        self, mock_delete, mock_ingest, temp_raw_data_dir, temp_db_path, sample_pages
    ):
        """Test updating when no existing data exists (like initial add)."""
        # Arrange: Create empty library directory
        lib_dir = temp_raw_data_dir / "testlib" / "latest"
        lib_dir.mkdir(parents=True)

        # Act: Perform update with new pages
        summary = perform_update(
            extracted_pages=sample_pages,
            library_name="testlib",
            version="latest",
            raw_data_dir=lib_dir,
            db_path=temp_db_path,
            table_name="test_table",
        )

        # Assert: All pages should be added
        assert summary["added"] == 3
        assert summary["modified"] == 0
        assert summary["deleted"] == 0
        assert summary["unchanged"] == 0

        # Should call ingest but not delete
        mock_ingest.assert_called_once()
        mock_delete.assert_not_called()

        # Files should be created
        assert len(list(lib_dir.glob("*.json"))) == 3

    @patch("openground.ingest.ingest_pages_to_lancedb")
    @patch("openground.update.delete_urls")
    def test_incremental_update_no_changes(
        self, mock_delete, mock_ingest, temp_raw_data_dir, temp_db_path, sample_pages
    ):
        """Test update when nothing has changed."""
        from urllib.parse import urlparse

        # Arrange: Create library directory with existing pages (same content)
        lib_dir = temp_raw_data_dir / "testlib" / "latest"
        lib_dir.mkdir(parents=True)

        for page in sample_pages:
            # Use same slug logic as update.py
            slug = urlparse(page["url"]).path.strip("/").replace("/", "-") or "home"
            with open(lib_dir / f"{slug}.json", "w") as f:
                json.dump(page, f)

        # Act: Perform update with same pages
        summary = perform_update(
            extracted_pages=sample_pages,
            library_name="testlib",
            version="latest",
            raw_data_dir=lib_dir,
            db_path=temp_db_path,
            table_name="test_table",
        )

        # Assert: Nothing should change
        assert summary["added"] == 0
        assert summary["modified"] == 0
        assert summary["deleted"] == 0
        assert summary["unchanged"] == 3

        # Should not call delete or ingest
        mock_delete.assert_not_called()
        mock_ingest.assert_not_called()

    @patch("openground.ingest.ingest_pages_to_lancedb")
    @patch("openground.update.delete_urls")
    def test_incremental_update_with_changes(
        self, mock_delete, mock_ingest, temp_raw_data_dir, temp_db_path
    ):
        """Test update with new, modified, and deleted pages."""
        from urllib.parse import urlparse

        # Arrange: Create library directory with existing pages
        lib_dir = temp_raw_data_dir / "testlib" / "latest"
        lib_dir.mkdir(parents=True)

        existing_pages = [
            ParsedPage(
                url="https://example.com/page1",
                library_name="testlib",
                version="latest",
                title="Page 1",
                description="First page",
                last_modified=None,
                content="ORIGINAL content",  # Will be modified
            ),
            ParsedPage(
                url="https://example.com/page2",
                library_name="testlib",
                version="latest",
                title="Page 2",
                description="Second page",
                last_modified=None,
                content="Content of page 2",  # Will be deleted
            ),
        ]

        for page in existing_pages:
            # Use same slug logic as update.py
            slug = urlparse(page["url"]).path.strip("/").replace("/", "-") or "home"
            with open(lib_dir / f"{slug}.json", "w") as f:
                json.dump(page, f)

        # New extraction: page1 modified, page3 new, page2 deleted
        extracted_pages = [
            ParsedPage(
                url="https://example.com/page1",
                library_name="testlib",
                version="latest",
                title="Page 1 Updated",
                description="Updated page",
                last_modified=None,
                content="MODIFIED content",
            ),
            ParsedPage(
                url="https://example.com/page3",
                library_name="testlib",
                version="latest",
                title="Page 3",
                description="New page",
                last_modified=None,
                content="New content",
            ),
        ]

        # Act: Perform update
        summary = perform_update(
            extracted_pages=extracted_pages,
            library_name="testlib",
            version="latest",
            raw_data_dir=lib_dir,
            db_path=temp_db_path,
            table_name="test_table",
        )

        # Assert: Correct counts for each category
        assert summary["added"] == 1  # page3
        assert summary["modified"] == 1  # page1
        assert summary["deleted"] == 1  # page2
        assert summary["unchanged"] == 0

        # Should delete old chunks and add new ones
        mock_delete.assert_called_once()
        mock_ingest.assert_called_once()

        # Verify files were updated correctly
        json_files = list(lib_dir.glob("*.json"))
        assert len(json_files) == 2  # page1 and page3
        assert not any("page2" in f.name for f in json_files)


class TestDeleteUrls:
    """Test the delete_urls function in query.py."""

    def test_delete_empty_list(self, temp_db_path):
        """Should handle empty URL list gracefully."""
        from openground.query import delete_urls

        # Arrange: Empty URL list
        urls = []

        # Act: Try to delete with empty list
        count = delete_urls(
            urls=urls,
            library_name="testlib",
            version="latest",
            db_path=temp_db_path,
            table_name="test_table",
        )

        # Assert: Should return 0 without error
        assert count == 0

    def test_delete_urls_escaping(self, temp_db_path):
        """Should properly escape special characters in URLs."""
        from openground.query import delete_urls
        import lancedb
        import pyarrow as pa

        # Arrange: Create test table with URL containing special characters
        db = lancedb.connect(str(temp_db_path))
        schema = pa.schema([
            pa.field("url", pa.string()),
            pa.field("library_name", pa.string()),
            pa.field("version", pa.string()),
            pa.field("content", pa.string()),
        ])
        table = db.create_table("test_table", data=[], schema=schema)

        special_url = "https://example.com/page?foo=bar&baz=qux'test"
        table.add([{
            "url": special_url,
            "library_name": "testlib",
            "version": "latest",
            "content": "test",
        }])

        # Act: Delete the URL with special characters
        count = delete_urls(
            urls=[special_url],
            library_name="testlib",
            version="latest",
            db_path=temp_db_path,
            table_name="test_table",
        )

        # Assert: Should delete exactly 1 row without raising SQL error
        assert count == 1


class TestLibraryVersionExists:
    """Test the library_version_exists function in query.py."""

    def test_nonexistent_library(self, temp_db_path):
        """Should return False for nonexistent library."""
        from openground.query import library_version_exists

        # Arrange: Nonexistent library name
        library = "nonexistent"

        # Act: Check if library exists
        result = library_version_exists(
            library_name=library,
            version="latest",
            db_path=temp_db_path,
            table_name="test_table",
        )

        # Assert: Should return False
        assert result is False
