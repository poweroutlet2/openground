import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from openground.cli import app

runner = CliRunner()

@pytest.fixture
def mock_config():
    """Mock the effective configuration to avoid reading actual config files."""
    with patch("openground.cli.get_effective_config") as mock:
        mock.return_value = {
            "extraction": {"concurrency_limit": 5},
            "db_path": "~/.openground/data",
            "table_name": "docs",
            "raw_data_dir": "~/.openground/raw_data",
            "sources": {"auto_add_local": True}
        }
        yield mock

@pytest.fixture
def mock_path_utils():
    """Mock Path methods to avoid actual filesystem operations."""
    with patch("pathlib.Path.exists") as mock_exists, \
         patch("pathlib.Path.mkdir") as mock_mkdir, \
         patch("pathlib.Path.glob") as mock_glob:
        mock_exists.return_value = True
        mock_glob.return_value = []
        yield mock_exists, mock_mkdir, mock_glob

@pytest.fixture
def mock_ingest_pipeline():
    """Mock the heavy parts of the ingestion pipeline."""
    def mock_run(coro):
        """Silences 'coroutine never awaited' warning by closing the coroutine."""
        if hasattr(coro, "close"):
            coro.close()

    # Patch them in their defining modules because they are imported locally in the CLI command.
    with patch("openground.ingest.ingest_to_lancedb") as ingest, \
         patch("openground.ingest.load_parsed_pages") as load, \
         patch("openground.cli.asyncio.run", side_effect=mock_run) as run:
        yield ingest, load, run

def test_add_manual_source_ignores_sources_json(mock_config, mock_path_utils, mock_ingest_pipeline):
    """
    Test that providing a manual --source ignores the sources.json file.
    
    This test verifies that when the user specifies a source via the CLI, 
    the application does not attempt to look up configuration in the 
    sources configuration file, ensuring manual CLI options have priority.
    """
    with patch("openground.cli.get_library_config") as mock_get_config:
        # Run command with --source
        result = runner.invoke(app, ["add", "test-lib", "--source", "https://github.com/user/repo", "--yes"])
        
        assert result.exit_code == 0
        # get_library_config should NOT be called because source was provided
        mock_get_config.assert_not_called()

def test_add_manual_source_upserts_to_local_sources(mock_config, mock_path_utils, mock_ingest_pipeline):
    """
    Test that providing a manual --source upserts the configuration to the local sources.json.
    
    This test verifies that after a successful manual extraction/ingestion, 
    the source configuration is saved to the local sources.json file for 
    future use, assuming 'auto_add_local' is enabled.
    """
    with patch("openground.extract.source.save_source_to_local") as mock_save_local:
        # Run command with --source (detects as git_repo)
        result = runner.invoke(app, ["add", "test-lib", "--source", "https://github.com/user/repo", "--yes"])
        
        assert result.exit_code == 0
        # save_source_to_local should be called with the detected configuration
        mock_save_local.assert_called_once()
        args, _ = mock_save_local.call_args
        assert args[0] == "test-lib"
        assert args[1]["type"] == "git_repo"
        assert args[1]["repo_url"] == "https://github.com/user/repo"

def test_add_manual_sitemap_source_upserts_to_local_sources(mock_config, mock_path_utils, mock_ingest_pipeline):
    """
    Test that providing a manual sitemap --source upserts correctly.
    
    This test ensures that sitemap URLs are also correctly detected and 
    saved to the local sources.json.
    """
    with patch("openground.extract.source.save_source_to_local") as mock_save_local:
        # Run command with --source (detects as sitemap)
        result = runner.invoke(app, ["add", "test-lib", "--source", "https://example.com/sitemap.xml", "--yes"])
        
        assert result.exit_code == 0
        # save_source_to_local should be called with sitemap type
        mock_save_local.assert_called_once()
        args, _ = mock_save_local.call_args
        assert args[0] == "test-lib"
        assert args[1]["type"] == "sitemap"
        assert args[1]["sitemap_url"] == "https://example.com/sitemap.xml"
