import pytest

from openground.console import UserError
from openground.sources import get_source, load_sources, remove_source, save_source


def test_roundtrip(tmp_path):
    assert load_sources() == {}
    save_source("a", {"type": "sitemap", "sitemap_url": "https://x.dev/sitemap.xml"})
    save_source("b", {"type": "git_repo", "repo_url": "https://github.com/o/r.git"})

    assert get_source("a") == {
        "type": "sitemap",
        "sitemap_url": "https://x.dev/sitemap.xml",
    }
    assert set(load_sources()) == {"a", "b"}
    assert (tmp_path / "config" / "openground" / "sources.json").exists()


def test_remove_source():
    save_source("a", {"type": "local_path", "local_path": "/docs"})
    assert remove_source("a") is True
    assert remove_source("a") is False
    assert get_source("a") is None


def test_corrupt_file_raises_instead_of_being_overwritten(tmp_path):
    path = tmp_path / "config" / "openground" / "sources.json"
    path.parent.mkdir(parents=True)
    path.write_text("{oops")

    with pytest.raises(UserError, match="Invalid sources file"):
        load_sources()
    with pytest.raises(UserError):
        save_source("a", {"type": "local_path", "local_path": "/docs"})
    assert path.read_text() == "{oops"
