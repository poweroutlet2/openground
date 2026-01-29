"""
Tests to verify that the isolation sandbox is working correctly.
Run this FIRST to ensure tests won't touch your real data.
"""
import os
from pathlib import Path
from openground.config import get_data_home, get_config_path


def test_data_dir_is_sandboxed():
    """Verify data directory points to temp location, not real user home."""
    current_path = str(get_data_home())

    # Should contain openground
    assert "openground" in current_path

    # Should be in pytest's temp directory
    assert "pytest" in current_path or "tmp" in current_path

    # Should NOT be the real user home
    real_home = str(Path.home())
    assert not current_path.startswith(real_home + "/.local")
    assert not current_path.startswith(real_home + "\\AppData\\Local")


def test_config_dir_is_sandboxed():
    """Verify config directory points to temp location."""
    config_path = str(get_config_path())

    # Should be in temp directory
    assert "pytest" in config_path or "tmp" in config_path

    # Should NOT be the real user config
    real_config = str(Path.home() / ".config" / "openground")
    assert not config_path.startswith(real_config)


def test_libraries_dont_leak_between_tests():
    """Test that data from one test doesn't leak to another."""
    from openground.ingest import load_parsed_pages

    # This test should run with empty data directory
    data_home = get_data_home()
    raw_data_base = data_home / "raw_data"

    # Should be empty (no data from previous tests)
    if raw_data_base.exists():
        # Count any library directories
        lib_count = len([d for d in raw_data_base.iterdir() if d.is_dir()])
        assert lib_count == 0, "Data leaked from previous test!"
