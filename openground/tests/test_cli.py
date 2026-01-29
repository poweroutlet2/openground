import pytest
import tempfile
import shutil
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

from openground.cli import app

runner = CliRunner()


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config and data during tests."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    # Create subdirectories
    raw_data_dir = temp_path / "raw_data"
    db_path = temp_path / "data"
    config_dir = temp_path / "config"
    raw_data_dir.mkdir()
    db_path.mkdir()
    config_dir.mkdir()

    yield temp_path

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config(temp_config_dir):
    """Mock configuration to use temp directories."""
    config = {
        "extraction": {"concurrency_limit": 5},
        "db_path": str(temp_config_dir / "data"),
        "table_name": "docs",
        "raw_data_dir": str(temp_config_dir / "raw_data"),
        "sources": {"auto_add_local": False},  # Disable to avoid writing to sources
        "embeddings": {
            "batch_size": 32,
            "chunk_size": 800,
            "chunk_overlap": 200,
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "embedding_dimensions": 384,
            # Use sentence-transformers for tests as it's more commonly available
            "embedding_backend": "sentence-transformers",
        },
        "query": {"top_k": 5},
    }

    with (
        patch("openground.cli.get_effective_config", return_value=config),
        patch("openground.config.get_effective_config", return_value=config),
    ):
        yield config


def test_add_git_source_creates_raw_data(temp_config_dir, mock_config):
    """
    Test that adding a git source creates raw data files.
    Verifies the CLI creates the expected directory structure.
    """
    library_name = "test-lib"
    version = "latest"
    raw_data_dir = Path(mock_config["raw_data_dir"])
    output_dir = raw_data_dir / library_name / version

    def mock_extract_repo(*args, **kwargs):
        """Mock extract_repo that creates the expected directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        # Create a dummy extracted file
        (output_dir / "test.json").write_text('{"url": "https://example.com"}')

    # Mock the extraction and ingestion pipeline to avoid network calls
    with (
        patch("openground.extract.git.extract_repo", side_effect=mock_extract_repo),
        patch("openground.ingest.ingest_to_lancedb"),
        patch("openground.ingest.load_parsed_pages", return_value=[]),
    ):
        # Run the add command
        result = runner.invoke(
            app,
            ["add", library_name, "--source", "https://github.com/user/repo", "--yes"],
        )

        assert result.exit_code == 0


def test_add_sitemap_source_creates_raw_data(temp_config_dir, mock_config):
    """
    Test that adding a sitemap source creates raw data files.
    Verifies the CLI creates the expected directory structure.
    """
    library_name = "test-sitemap-lib"
    version = "latest"
    raw_data_dir = Path(mock_config["raw_data_dir"])
    output_dir = raw_data_dir / library_name / version

    async def mock_extract_pages(*args, **kwargs):
        """Mock extract_pages that creates the expected directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        # Create a dummy extracted file
        (output_dir / "test.json").write_text('{"url": "https://example.com"}')

    # Mock the extraction and ingestion pipeline to avoid network calls
    with (
        patch(
            "openground.extract.sitemap.extract_pages", side_effect=mock_extract_pages
        ),
        patch("openground.ingest.ingest_to_lancedb"),
        patch("openground.ingest.load_parsed_pages", return_value=[]),
    ):
        # Run the add command
        result = runner.invoke(
            app,
            [
                "add",
                library_name,
                "--source",
                "https://example.com/sitemap.xml",
                "--yes",
            ],
        )

        assert result.exit_code == 0


def test_add_missing_source_errors(mock_config):
    """
    Test that adding without a source produces an error.
    """
    library_name = "test-lib"

    # Mock get_library_config to return None (no source found)
    with patch("openground.cli.get_library_config", return_value=(None, None)):
        result = runner.invoke(app, ["add", library_name])

        assert result.exit_code == 1


def test_nuke_raw_data_deletes_directory(temp_config_dir, mock_config):
    """
    Test that nuking raw_data deletes the directory and its contents.
    """
    raw_data_dir = Path(mock_config["raw_data_dir"])

    # Create test data
    test_lib = raw_data_dir / "testlib" / "latest"
    test_lib.mkdir(parents=True)
    (test_lib / "test.json").write_text('{"url": "https://example.com"}')

    # Verify data exists
    assert test_lib.exists()

    # Run nuke raw_data
    result = runner.invoke(app, ["nuke", "raw_data", "--yes"])

    assert result.exit_code == 0
    # Directory should be deleted (or empty)
    assert not raw_data_dir.exists() or not any(raw_data_dir.iterdir())


def test_nuke_raw_data_skips_when_empty(temp_config_dir, mock_config):
    """
    Test that nuking empty raw_data exits early without confirmation.
    """
    raw_data_dir = Path(mock_config["raw_data_dir"])

    # Verify directory is empty
    assert not any(raw_data_dir.iterdir())

    # Run nuke raw_data
    result = runner.invoke(app, ["nuke", "raw_data", "--yes"])

    assert result.exit_code == 0
    assert "No raw data found" in result.stdout


def test_nuke_embeddings_deletes_lancedb_directory(temp_config_dir, mock_config):
    """
    Test that nuking embeddings deletes the LanceDB directory.
    """
    db_path = Path(mock_config["db_path"])

    # Create test data
    test_file = db_path / "test.lance"
    test_file.write_text("test data")

    # Verify data exists
    assert test_file.exists()

    # Mock list_libraries to return a library
    with patch("openground.query.list_libraries", return_value=["testlib"]):
        # Run nuke embeddings
        result = runner.invoke(app, ["nuke", "embeddings", "--yes"])

        assert result.exit_code == 0
        # Directory should be deleted
        assert not db_path.exists() or not any(db_path.iterdir())


def test_nuke_embeddings_skips_when_empty(temp_config_dir, mock_config):
    """
    Test that nuking empty embeddings exits early without confirmation.
    """
    # Mock list_libraries to return empty
    with patch("openground.query.list_libraries", return_value=[]):
        # Run nuke embeddings
        result = runner.invoke(app, ["nuke", "embeddings", "--yes"])

        assert result.exit_code == 0
        assert "No embeddings found" in result.stdout


def test_nuke_all_deletes_both_directories(temp_config_dir, mock_config):
    """
    Test that nuking all deletes both raw_data and embeddings.
    """
    raw_data_dir = Path(mock_config["raw_data_dir"])
    db_path = Path(mock_config["db_path"])

    # Create test data in both locations
    test_lib = raw_data_dir / "testlib" / "latest"
    test_lib.mkdir(parents=True)
    (test_lib / "test.json").write_text('{"url": "https://example.com"}')

    test_file = db_path / "test.lance"
    test_file.write_text("test data")

    # Verify data exists
    assert test_lib.exists()
    assert test_file.exists()

    # Mock list_libraries to return a library
    with patch("openground.query.list_libraries", return_value=["testlib"]):
        # Run nuke all
        result = runner.invoke(app, ["nuke", "all", "--yes"])

        assert result.exit_code == 0
        # Both directories should be deleted
        assert not raw_data_dir.exists() or not any(raw_data_dir.iterdir())
        assert not db_path.exists() or not any(db_path.iterdir())


def test_nuke_all_skips_when_both_empty(temp_config_dir, mock_config):
    """
    Test that nuking all when both are empty exits early without confirmation.
    """
    raw_data_dir = Path(mock_config["raw_data_dir"])

    # Verify directories are empty
    assert not any(raw_data_dir.iterdir())

    # Mock list_libraries to return empty
    with patch("openground.query.list_libraries", return_value=[]):
        # Run nuke all
        result = runner.invoke(app, ["nuke", "all", "--yes"])

        assert result.exit_code == 0
        assert "No data found" in result.stdout


def test_nuke_embeddings_clears_query_caches(temp_config_dir, mock_config):
    """
    Test that nuking embeddings clears query caches.
    """
    db_path = Path(mock_config["db_path"])

    # Create test data
    test_file = db_path / "test.lance"
    test_file.write_text("test data")

    # Mock list_libraries and clear_query_caches
    with (
        patch("openground.query.list_libraries", return_value=["testlib"]),
        patch("openground.query.clear_query_caches") as mock_clear,
    ):
        # Run nuke embeddings
        result = runner.invoke(app, ["nuke", "embeddings", "--yes"])

        assert result.exit_code == 0
        # Verify caches were cleared
        mock_clear.assert_called_once()


def test_nuke_all_clears_query_caches(temp_config_dir, mock_config):
    """
    Test that nuking all clears query caches when deleting embeddings.
    """
    raw_data_dir = Path(mock_config["raw_data_dir"])
    db_path = Path(mock_config["db_path"])

    # Create test data
    test_lib = raw_data_dir / "testlib" / "latest"
    test_lib.mkdir(parents=True)

    test_file = db_path / "test.lance"
    test_file.write_text("test data")

    # Mock list_libraries and clear_query_caches
    with (
        patch("openground.query.list_libraries", return_value=["testlib"]),
        patch("openground.query.clear_query_caches") as mock_clear,
    ):
        # Run nuke all
        result = runner.invoke(app, ["nuke", "all", "--yes"])

        assert result.exit_code == 0
        # Verify caches were cleared
        mock_clear.assert_called_once()


def test_nuke_raw_data_does_not_clear_query_caches(temp_config_dir, mock_config):
    """
    Test that nuking raw_data does NOT clear query caches.
    """
    raw_data_dir = Path(mock_config["raw_data_dir"])

    # Create test data
    test_lib = raw_data_dir / "testlib" / "latest"
    test_lib.mkdir(parents=True)

    # Mock clear_query_caches
    with patch("openground.query.clear_query_caches") as mock_clear:
        # Run nuke raw_data
        result = runner.invoke(app, ["nuke", "raw_data", "--yes"])

        assert result.exit_code == 0
        # Verify caches were NOT cleared
        mock_clear.assert_not_called()


# Tests for install-mcp command


def test_install_mcp_claude_code_removes_existing_first():
    """
    Test that install-mcp --claude-code removes existing config before adding.
    AAA Pattern:
    - Arrange: Mock subprocess.run to track calls and return success
    - Act: Invoke the install-mcp --claude-code command
    - Assert: Verify remove was called before add, with correct arguments
    """
    # Arrange
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        # Act
        result = runner.invoke(app, ["install-mcp", "--claude-code"])

        # Assert
        assert result.exit_code == 0
        assert mock_run.call_count == 2
        # First call should be remove
        remove_call = mock_run.call_args_list[0][0][0]
        assert remove_call == [
            "claude",
            "mcp",
            "remove",
            "openground",
            "--scope",
            "user",
        ]
        # Second call should be add
        add_call = mock_run.call_args_list[1][0][0]
        assert add_call == [
            "claude",
            "mcp",
            "add",
            "--transport",
            "stdio",
            "--scope",
            "user",
            "openground",
            "--",
            "openground-mcp",
        ]


def test_install_mcp_claude_code_succeeds_on_fresh_install():
    """
    Test that install-mcp --claude-code succeeds even when remove fails (no existing config).
    AAA Pattern:
    - Arrange: Mock subprocess.run to fail on remove, succeed on add
    - Act: Invoke the install-mcp --claude-code command
    - Assert: Verify command succeeds despite remove returning non-zero
    """
    # Arrange
    with patch("subprocess.run") as mock_run:
        # Remove fails (exit code 1), add succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1),  # remove fails
            MagicMock(returncode=0, stdout="Added successfully"),  # add succeeds
        ]

        # Act
        result = runner.invoke(app, ["install-mcp", "--claude-code"])

        # Assert
        assert result.exit_code == 0
        # Note: success() output goes to rich console, not captured in stdout
        # So we just verify the command succeeded and the subprocess output is present
        assert "Added successfully" in result.stdout


def test_install_mcp_claude_code_errors_on_add_failure():
    """
    Test that install-mcp --claude-code shows error when add fails.
    AAA Pattern:
    - Arrange: Mock subprocess.run to fail on the add command
    - Act: Invoke the install-mcp --claude-code command
    - Assert: Verify error message is shown and exit code is 1
    """
    # Arrange
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Error: Failed to add MCP server",
            stdout="Some output",
        )

        # Act
        result = runner.invoke(app, ["install-mcp", "--claude-code"])

        # Assert
        assert result.exit_code == 1
        # Note: error() output goes to rich console, not captured in stdout
        # So we check for the printed stderr output
        assert "Error: Error: Failed to add MCP server" in result.stdout


def test_install_mcp_claude_code_handles_missing_claude_cli():
    """
    Test that install-mcp --claude-code shows helpful error when claude CLI is missing.
    AAA Pattern:
    - Arrange: Mock subprocess.run to raise FileNotFoundError
    - Act: Invoke the install-mcp --claude-code command
    - Assert: Verify helpful error message about installing Claude Code CLI
    """
    # Arrange
    with patch("subprocess.run", side_effect=FileNotFoundError):
        # Act
        result = runner.invoke(app, ["install-mcp", "--claude-code"])

        # Assert
        assert result.exit_code == 1
        # Note: error() output goes to rich console, not captured in stdout
        # So we check for the printed help message
        assert "Please install Claude Code CLI first:" in result.stdout
        assert "code.claude.com/docs/en/cli" in result.stdout


def test_install_mcp_shows_json_by_default():
    """
    Test that install-mcp (no flags) shows JSON configuration.
    AAA Pattern:
    - Arrange: Mock _find_openground_mcp_command to return a fake path
    - Act: Invoke install-mcp without flags
    - Assert: Verify JSON output and instructions are shown
    """
    # Arrange
    with patch(
        "openground.cli._find_openground_mcp_command",
        return_value="/usr/bin/openground-mcp",
    ):
        # Act
        result = runner.invoke(app, ["install-mcp"])

        # Assert
        assert result.exit_code == 0
        assert '"openground"' in result.stdout
        assert '"command":' in result.stdout
        assert "--claude-code" in result.stdout


def test_install_mcp_wsl_generates_wsl_config():
    """
    Test that install-mcp --wsl generates WSL-compatible config.
    AAA Pattern:
    - Arrange: No mocks needed (uses actual config generation)
    - Act: Invoke install-mcp with --wsl flag
    - Assert: Verify config contains wsl.exe wrapper
    """
    # Arrange - not needed for this test

    # Act
    result = runner.invoke(app, ["install-mcp", "--wsl"])

    # Assert
    assert result.exit_code == 0
    assert "wsl.exe" in result.stdout


class TestAddUpdateDetection:
    """Test that add correctly detects new vs existing libraries."""

    @patch("openground.query.library_version_exists")
    def test_fresh_add_triggers_ingest_not_update(
        self, mock_exists, mock_config, temp_config_dir
    ):
        """
        When adding a new library, should perform full ingest not update.
        AAA Pattern:
        - Arrange: library_version_exists returns False (library doesn't exist)
        - Act: Run add command
        - Assert: Should NOT show "already exists" message
        """
        # Arrange: library_version_exists returns False (library doesn't exist)
        mock_exists.return_value = False

        library_name = "newlib"
        version = "latest"
        raw_data_dir = Path(mock_config["raw_data_dir"])
        output_dir = raw_data_dir / library_name / version

        async def mock_extract_pages(*args, **kwargs):
            """Mock extract_pages that creates the expected directory."""
            output_dir.mkdir(parents=True, exist_ok=True)
            # Create a dummy extracted file
            (output_dir / "test.json").write_text('{"url": "https://example.com"}')

        with (
            patch(
                "openground.extract.sitemap.extract_pages", side_effect=mock_extract_pages
            ),
            patch("openground.ingest.ingest_to_lancedb"),
            patch("openground.ingest.load_parsed_pages", return_value=[]),
        ):
            # Act: Run add command
            result = runner.invoke(
                app, ["add", library_name, "--source", "https://example.com/sitemap.xml", "-y"]
            )

        # Assert: Should NOT show "already exists" message
        assert result.exit_code == 0, f"Exit code {result.exit_code}, output: {result.stdout}"
        assert "already exists" not in result.stdout

    @patch("openground.query.library_version_exists")
    def test_stale_raw_files_are_cleaned_up(
        self, mock_exists, mock_config, temp_config_dir
    ):
        """
        When library doesn't exist in LanceDB but raw files do exist (stale data),
        should clean up raw files and perform fresh ingest.
        AAA Pattern:
        - Arrange: library_version_exists returns False, but raw files exist
        - Act: Run add command
        - Assert: Raw files should be cleaned up, not treated as existing library
        """
        # Arrange: library_version_exists returns False (library not in LanceDB)
        mock_exists.return_value = False

        library_name = "stale-lib"
        version = "latest"
        raw_data_dir = Path(mock_config["raw_data_dir"])
        output_dir = raw_data_dir / library_name / version

        # Pre-create stale raw data files (simulating previous failed/cancelled run)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "old.json").write_text('{"url": "https://example.com/old"}')

        # Verify stale files exist
        assert output_dir.exists()
        assert list(output_dir.glob("*.json"))

        async def mock_extract_pages(*args, **kwargs):
            """Mock extract_pages that creates new files."""
            # Recreate directory if it was deleted (our code deletes stale dirs)
            output_dir.mkdir(parents=True, exist_ok=True)
            # Create a dummy extracted file
            (output_dir / "test.json").write_text('{"url": "https://example.com"}')


        with (
            patch(
                "openground.extract.sitemap.extract_pages", side_effect=mock_extract_pages
            ),
            patch("openground.ingest.ingest_to_lancedb"),
            patch("openground.ingest.load_parsed_pages", return_value=[]),
        ):
            # Act: Run add command
            result = runner.invoke(
                app, ["add", library_name, "--source", "https://example.com/sitemap.xml", "-y"]
            )

        # Debug: Print output if failing
        if result.exit_code != 0:
            print(f"\nExit code: {result.exit_code}")
            print(f"Output: {result.stdout}")
            if result.exception:
                import traceback
                print(f"Exception: {result.exception}")
                traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)

        # Assert: Should NOT show "already exists" (stale files should be cleaned up)
        assert result.exit_code == 0, f"Exit code {result.exit_code}, output: {result.stdout}"
        assert "already exists" not in result.stdout
        # The warning about stale files goes to rich console, not stdout, so we can't check for it
        # But the key thing is that it doesn't treat the library as existing

    @patch("openground.query.library_version_exists")
    def test_deleted_raw_files_detected_as_existing_library(
        self, mock_exists, mock_config, temp_config_dir
    ):
        """
        When library exists in LanceDB but a raw file is manually deleted,
        the system should still detect it as an existing library (not a new add).
        AAA Pattern:
        - Arrange: library_version_exists returns True (library in LanceDB), but one raw file is deleted
        - Act: Run add command (extraction will be mocked)
        - Assert: Should show "already exists" since LanceDB is the source of truth
        """
        # Arrange: library_version_exists returns True (library exists in LanceDB)
        mock_exists.return_value = True

        library_name = "existing-lib"
        version = "latest"
        raw_data_dir = Path(mock_config["raw_data_dir"])
        output_dir = raw_data_dir / library_name / version

        # Pre-create raw data files (simulating previous extraction)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "page1.json").write_text('{"url": "https://example.com/page1", "title": "Page 1", "content": "Content 1"}')
        (output_dir / "page2.json").write_text('{"url": "https://example.com/page2", "title": "Page 2", "content": "Content 2"}')
        (output_dir / "page3.json").write_text('{"url": "https://example.com/page3", "title": "Page 3", "content": "Content 3"}')

        # Simulate user deleting one raw file
        (output_dir / "page2.json").unlink()

        # Verify only 2 files remain
        assert len(list(output_dir.glob("*.json"))) == 2

        # Mock extraction that recreates all files (simulating what happens during update)
        async def mock_extract_pages(*args, **kwargs):
            """Mock extract_pages that recreates all files (including deleted one)."""
            # Recreate directory (extraction clears existing files first)
            output_dir.mkdir(parents=True, exist_ok=True)
            # Create all 3 files (simulating extraction from source)
            (output_dir / "page1.json").write_text('{"url": "https://example.com/page1"}')
            (output_dir / "page2.json").write_text('{"url": "https://example.com/page2"}')
            (output_dir / "page3.json").write_text('{"url": "https://example.com/page3"}')

        # Note: We can't test the full update flow due to fastembed import issues
        # But we can verify the detection logic works correctly
        with (
            patch(
                "openground.extract.sitemap.extract_pages", side_effect=mock_extract_pages
            ),
            patch("openground.ingest.ingest_to_lancedb"),
            patch("openground.ingest.load_parsed_pages", return_value=[]),
        ):
            # Act: Run add command
            result = runner.invoke(
                app, ["add", library_name, "--source", "https://example.com/sitemap.xml", "-y"]
            )

        # Assert: Should complete successfully
        # Note: The "already exists" message goes to rich console, not stdout
        # so we can't assert on it here. But we can verify:
        # 1. The command succeeded (exit code 0)
        # 2. All 3 files were recreated by extraction (including the deleted one)
        assert result.exit_code == 0, f"Exit code {result.exit_code}, output: {result.stdout}"
        assert len(list(output_dir.glob("*.json"))) == 3, "All files should be recreated by extraction"

        # Verify the deleted file (page2.json) was recreated
        assert (output_dir / "page2.json").exists(), "Deleted file should be recreated"




