import json
from pathlib import Path
from unittest.mock import patch
import pytest
from openground.extract.source import (
    get_source_file_path,
    save_source_to_local,
    load_source_file,
    get_library_config,
    LibrarySource,
)

@pytest.fixture(autouse=True)
def mock_default_local_source(monkeypatch, tmp_path):
    """Redirect DEFAULT_LOCAL_SOURCE_FILE to a temporary path for all tests in this module."""
    local_dir = tmp_path / ".openground_test"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_file = local_dir / "sources_test.json"
    
    import openground.config
    monkeypatch.setattr(openground.config, "DEFAULT_LOCAL_SOURCE_FILE", local_file)
    return local_file

def test_get_source_file_path_custom():
    """Test that a custom path is returned if provided."""
    custom_path = Path("/tmp/custom_sources.json")
    assert get_source_file_path(custom_path) == custom_path

def test_get_source_file_path_priority(mock_default_local_source):
    """Test the priority of source file resolution."""
    local_file = mock_default_local_source
    local_file.touch()

    # 1. Local file should take priority
    assert get_source_file_path() == local_file

    # 2. If local doesn't exist, try package-level (mocking existence)
    local_file.unlink()
    
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
                if "extract" in path_str: # package level
                    return True
            return False
        
        mock_exists.side_effect = side_effect
        path = get_source_file_path()
        assert "extract" in str(path)
        assert path.name == "sources.json"

def test_save_and_load_source(mock_default_local_source):
    """Test saving a source to local and loading it back."""
    local_file = mock_default_local_source

    config: LibrarySource = {
        "type": "sitemap",
        "sitemap_url": "https://example.com/sitemap.xml",
        "filter_keywords": ["docs"]
    }
    
    # Save
    save_source_to_local("test-lib", config)
    assert local_file.exists()
    
    # Load
    sources = load_source_file(local_file)
    assert "test-lib" in sources
    assert sources["test-lib"]["type"] == "sitemap"
    assert sources["test-lib"]["sitemap_url"] == "https://example.com/sitemap.xml"

def test_save_source_to_local_merges(mock_default_local_source):
    """Test that save_source_to_local merges with existing sources."""
    local_file = mock_default_local_source
    
    existing_sources = {
        "existing-lib": {"type": "git_repo", "repo_url": "https://github.com/org/repo"}
    }
    with open(local_file, "w") as f:
        json.dump(existing_sources, f)

    new_config: LibrarySource = {
        "type": "sitemap",
        "sitemap_url": "https://example.com/sitemap.xml"
    }
    
    save_source_to_local("new-lib", new_config)
    
    with open(local_file, "r") as f:
        saved_sources = json.load(f)
        
    assert "existing-lib" in saved_sources
    assert "new-lib" in saved_sources
    assert saved_sources["new-lib"]["type"] == "sitemap"

def test_get_library_config(tmp_path):
    """Test retrieving a specific library configuration."""
    sources_file = tmp_path / "sources.json"
    sources_data = {
        "lib1": {"type": "sitemap", "sitemap_url": "url1"},
        "lib2": {"type": "git_repo", "repo_url": "url2"}
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

def test_get_library_config_fallback(mock_default_local_source, tmp_path):
    """Test that get_library_config falls back to global if not in local."""
    local_file = mock_default_local_source
    local_data = {"local-lib": {"type": "sitemap", "sitemap_url": "local-url"}}
    with open(local_file, "w") as f:
        json.dump(local_data, f)
    
    # We want to test fallback to global. 
    # Global is Path(__file__).parent / "sources.json" OR Path(__file__).parent.parent / "sources.json"
    # We can mock patch('pathlib.Path.exists') and open to simulate global file.
    
    global_file = Path(__file__).parent / "sources.json"
    global_data = {"global-lib": {"type": "git_repo", "repo_url": "global-url"}}
    
    with patch("pathlib.Path.exists") as mock_exists:
        def side_effect(self):
            if str(self) == str(local_file):
                return True
            if str(self) == str(global_file):
                return True
            return False
        mock_exists.side_effect = side_effect
        
        # We also need to mock open to return different content based on path
        import builtins
        real_open = builtins.open
        
        def mocked_open(path, *args, **kwargs):
            if str(path) == str(global_file):
                from unittest.mock import mock_open
                return mock_open(read_data=json.dumps(global_data))()
            return real_open(path, *args, **kwargs)
            
        with patch("builtins.open", side_effect=mocked_open):
            # 1. Should find in local
            config, path = get_library_config("local-lib")
            assert config is not None
            assert str(path) == str(local_file)
            
            # 2. Should fallback to global
            config, path = get_library_config("global-lib")
            assert config is not None
            assert str(path) == str(global_file)
            assert config["type"] == "git_repo"
            
            # 3. Should not find
            config, path = get_library_config("missing-lib")
            assert config is None
            assert path is None

