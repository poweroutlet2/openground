"""
Tests to verify that the isolation sandbox is working correctly.
Run this FIRST to ensure tests won't touch your real data.
"""

from pathlib import Path
from openground.config import (
    get_data_home,
    get_config_path,
    get_default_config,
)


def test_data_dir_is_sandboxed():
    """Verify data directory points to temp location, not real user home."""
    current = Path(get_data_home())

    # Should contain openground
    assert "openground" in str(current)

    # Should be in pytest's temp directory
    assert "pytest" in str(current) or "tmp" in str(current)

    # Should NOT live inside the real data home. Comparing against the real
    # data home itself (not against Path.home()) is what makes this valid on
    # Windows, where pytest's tmp_path already sits under %LOCALAPPDATA%\Temp
    # and therefore inside the user home.
    real_data_home = Path(get_default_config()["raw_data_dir"]).parent

    assert current != real_data_home
    assert not current.is_relative_to(real_data_home), (
        f"sandboxed data dir leaked into the real data home: {current}"
    )


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

    # This test should run with empty data directory
    data_home = get_data_home()
    raw_data_base = data_home / "raw_data"

    # Should be empty (no data from previous tests)
    if raw_data_base.exists():
        # Count any library directories
        lib_count = len([d for d in raw_data_base.iterdir() if d.is_dir()])
        assert lib_count == 0, "Data leaked from previous test!"
