import json
from pathlib import Path
from unittest.mock import patch
import pytest
from openground.extract.source import (
    get_source_file_path,
    save_source_to_sources,
    load_source_file,
    get_library_config,
    LibrarySource,
)


@pytest.fixture(autouse=True)
def mock_user_source_file(monkeypatch, tmp_path):
    """Redirect USER_SOURCE_FILE and PROJECT_SOURCE_FILE to temporary paths for all tests in this module."""
    user_dir = tmp_path / ".openground_test_user"
    user_dir.mkdir(parents=True, exist_ok=True)
    user_file = user_dir / "sources_test.json"

    project_dir = tmp_path / ".openground_test_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    project_file = project_dir / "sources_test.json"

    import openground.config

    monkeypatch.setattr(openground.config, "USER_SOURCE_FILE", user_file)
    monkeypatch.setattr(openground.config, "PROJECT_SOURCE_FILE", project_file)
    return user_file, project_file


def test_get_source_file_path_custom():
    """Test that a custom path is returned if provided."""
    custom_path = Path("/tmp/custom_sources.json")
    assert get_source_file_path(custom_path) == custom_path


def test_get_source_file_path_priority(mock_user_source_file):
    """Test the priority of source file resolution."""
    user_file, project_file = mock_user_source_file
    project_file.touch()

    # 1. Project-local file should take priority
    assert get_source_file_path() == project_file

    # 2. If project doesn't exist, try user sources
    project_file.unlink()
    user_file.touch()

    assert get_source_file_path() == user_file

    # 3. If user doesn't exist, try package-level (mocking existence)
    user_file.unlink()

    with patch("pathlib.Path.exists") as mock_exists:
        # Mocking Path.exists can affect other operations.
        # This test focuses on the resolution logic in get_source_file_path.

        # Mock pkg_source_file.exists() to True
        # Path(__file__).parent / "sources.json"
        def side_effect(*args, **kwargs):
            if not args:
                return False
            path_obj = args[0]
            path_str = str(path_obj)
            if "sources.json" in path_str:
                if "extract" in path_str:  # package level
                    return True
            return False

        mock_exists.side_effect = side_effect
        path = get_source_file_path()
        assert "extract" in str(path)
        assert path.name == "sources.json"


def test_save_and_load_source(mock_user_source_file):
    """Test saving a source to both project-local and user, and loading it back."""
    user_file, project_file = mock_user_source_file

    config: LibrarySource = {
        "type": "sitemap",
        "sitemap_url": "https://example.com/sitemap.xml",
        "filter_keywords": ["docs"],
    }

    # Save
    save_source_to_sources("test-lib", config)

    # Both files should exist with the source
    assert user_file.exists()
    assert project_file.exists()

    # Load from user file
    sources = load_source_file(user_file)
    assert "test-lib" in sources
    assert sources["test-lib"]["type"] == "sitemap"
    assert sources["test-lib"]["sitemap_url"] == "https://example.com/sitemap.xml"

    # Load from project file
    sources = load_source_file(project_file)
    assert "test-lib" in sources
    assert sources["test-lib"]["type"] == "sitemap"


def test_save_source_to_user_merges(mock_user_source_file):
    """Test that save_source_to_user merges with existing sources in both files."""
    user_file, project_file = mock_user_source_file

    # Pre-populate both files with different existing sources
    user_existing = {
        "user-lib": {"type": "git_repo", "repo_url": "https://github.com/user/repo"}
    }
    with open(user_file, "w") as f:
        json.dump(user_existing, f)

    project_existing = {
        "project-lib": {
            "type": "sitemap",
            "sitemap_url": "https://project.com/sitemap.xml",
        }
    }
    with open(project_file, "w") as f:
        json.dump(project_existing, f)

    new_config: LibrarySource = {
        "type": "sitemap",
        "sitemap_url": "https://example.com/sitemap.xml",
    }

    save_source_to_sources("new-lib", new_config)

    # Check user file - should have both existing and new
    with open(user_file, "r") as f:
        user_sources = json.load(f)
    assert "user-lib" in user_sources
    assert "new-lib" in user_sources
    assert user_sources["new-lib"]["type"] == "sitemap"

    # Check project file - should have both existing and new
    with open(project_file, "r") as f:
        project_sources = json.load(f)
    assert "project-lib" in project_sources
    assert "new-lib" in project_sources
    assert project_sources["new-lib"]["type"] == "sitemap"


def test_get_library_config(tmp_path):
    """Test retrieving a specific library configuration."""
    sources_file = tmp_path / "sources.json"
    sources_data = {
        "lib1": {"type": "sitemap", "sitemap_url": "url1"},
        "lib2": {"type": "git_repo", "repo_url": "url2"},
    }
    with open(sources_file, "w") as f:
        json.dump(sources_data, f)

    # Test existing
    config, path = get_library_config("lib1", custom_path=sources_file)
    assert config is not None
    assert path == sources_file
    assert config["type"] == "sitemap"

    # Test non-existing
    config, path = get_library_config("non-existent", custom_path=sources_file)
    assert config is None
    assert path is None


def test_get_library_config_fallback(mock_user_source_file, tmp_path):
    """Test that get_library_config falls back to user sources if not in project-local."""
    user_file, project_file = mock_user_source_file
    project_data = {"project-lib": {"type": "sitemap", "sitemap_url": "project-url"}}
    with open(project_file, "w") as f:
        json.dump(project_data, f)

    user_data = {"user-lib": {"type": "git_repo", "repo_url": "user-url"}}
    with open(user_file, "w") as f:
        json.dump(user_data, f)

    # 1. Should find in project-local first
    config, path = get_library_config("project-lib")
    assert config is not None
    assert path == project_file
    assert config["type"] == "sitemap"

    # 2. Should fallback to user sources
    config, path = get_library_config("user-lib")
    assert config is not None
    assert path == user_file
    assert config["type"] == "git_repo"

    # 3. Should not find
    config, path = get_library_config("missing-lib")
    assert config is None
    assert path is None


def test_project_local_priority(mock_user_source_file):
    """Test that project-local sources take priority over user sources."""
    user_file, project_file = mock_user_source_file

    # Create user sources
    user_sources = {"lib1": {"type": "sitemap", "sitemap_url": "user-url"}}
    with open(user_file, "w") as f:
        json.dump(user_sources, f)

    # Create project-local sources
    project_sources = {"lib1": {"type": "git_repo", "repo_url": "project-url"}}
    with open(project_file, "w") as f:
        json.dump(project_sources, f)

    # get_library_config should find project-local first
    config, path = get_library_config("lib1")
    assert config["type"] == "git_repo"
    assert config["repo_url"] == "project-url"
    assert path == project_file
