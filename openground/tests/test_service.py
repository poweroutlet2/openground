import pytest

from openground.query import library_version_exists, list_libraries_with_versions
from openground.service import (
    ServiceError,
    add_library,
    detect_source_type,
    list_libraries,
    parse_source,
    remove_library,
    reset_data,
    resolve_version,
    update_libraries,
)
from openground.config import get_data_home, get_library_raw_data_dir
from openground.sources import get_source

GIT = "https://github.com/example/example.git"
SITEMAP = "https://docs.example.com/sitemap.xml"


class TestDetectSourceType:
    @pytest.mark.parametrize(
        "source",
        [
            "https://github.com/user/repo",
            "https://github.com/user/repo/tree/v1.0/docs",
            "https://gitlab.com/group/project",
            "https://example.com/some/repo.git",
            "git@example.com:user/repo",
            "ssh://git@example.com/user/repo",
        ],
    )
    def test_git(self, source):
        assert detect_source_type(source) == "git_repo"

    @pytest.mark.parametrize(
        "source",
        [
            SITEMAP,
            "https://docs.example.com/",
            "http://docs.example.com/sitemap_index.xml",
        ],
    )
    def test_sitemap(self, source):
        assert detect_source_type(source) == "sitemap"

    @pytest.mark.parametrize(
        "source",
        [
            "/abs/missing",
            "~/docs",
            "./docs",
            "../docs",
            "C:\\docs",
            "C:/docs",
            "\\\\server\\share",
        ],
    )
    def test_local_path_patterns(self, source):
        assert detect_source_type(source) == "local_path"

    def test_existing_directory_wins_over_name(self, tmp_path, monkeypatch):
        (tmp_path / "docs").mkdir()
        monkeypatch.chdir(tmp_path)
        assert detect_source_type("docs") == "local_path"

    def test_unrecognized_source_errors(self):
        with pytest.raises(ServiceError, match="Could not tell"):
            detect_source_type("example.com/docs")


class TestParseSource:
    def test_git_web_url_yields_repo_ref_and_path(self):
        spec, ref = parse_source("https://github.com/user/repo/tree/v1.0/docs")
        assert spec == {
            "type": "git_repo",
            "repo_url": "https://github.com/user/repo.git",
            "docs_paths": ["docs"],
        }
        assert ref == "v1.0"

    def test_plain_git_url_has_no_ref(self):
        assert parse_source(GIT) == ({"type": "git_repo", "repo_url": GIT}, None)

    def test_sitemap(self):
        assert parse_source(SITEMAP) == (
            {"type": "sitemap", "sitemap_url": SITEMAP},
            None,
        )

    def test_local_path_is_made_absolute(self, tmp_path):
        spec, _ = parse_source(str(tmp_path))
        assert spec == {"type": "local_path", "local_path": str(tmp_path.resolve())}


class TestAddLibrary:
    def test_new_library_is_ingested_and_source_remembered(self, fake_source):
        result = add_library("lib", GIT, docs_paths=["docs"])

        assert (result.library, result.version, result.pages) == ("lib", "latest", 2)
        assert result.summary is None
        assert list_libraries_with_versions() == {"lib": ["latest"]}
        assert get_source("lib") == {
            "type": "git_repo",
            "repo_url": GIT,
            "docs_paths": ["docs"],
        }
        assert len(list(get_library_raw_data_dir("lib", "latest").glob("*.json"))) == 2
        assert fake_source.calls[0]["docs_paths"] == ["docs"]

    def test_rerun_updates_incrementally(self, fake_source):
        add_library("lib", SITEMAP)
        fake_source.pages = {
            "intro": "Intro page",
            "guide": "Changed",
            "new": "New page",
        }

        result = add_library("lib", SITEMAP)

        assert result.summary == {
            "added": 1,
            "deleted": 0,
            "modified": 1,
            "unchanged": 1,
        }
        assert len(list(get_library_raw_data_dir("lib", "latest").glob("*.json"))) == 3

    def test_remembered_source_is_reused(self, fake_source):
        add_library("lib", SITEMAP, filter_keywords=["guide"])
        add_library("lib")

        assert fake_source.calls[1]["sitemap_url"] == SITEMAP
        assert fake_source.calls[1]["filter_keywords"] == ["guide"]

    def test_flags_override_remembered_source(self, fake_source):
        add_library("lib", GIT, docs_paths=["docs"])
        add_library("lib", docs_paths=["wiki"])

        assert fake_source.calls[1]["docs_paths"] == ["wiki"]
        assert (get_source("lib") or {})["docs_paths"] == ["wiki"]

    def test_no_source_errors(self, fake_source):
        with pytest.raises(ServiceError, match="No remembered source"):
            add_library("lib")

    def test_version_only_for_git(self, fake_source):
        with pytest.raises(ServiceError, match="--version"):
            add_library("lib", SITEMAP, version="v2")
        assert get_source("lib") is None

    def test_git_version_is_used(self, fake_source):
        add_library("lib", GIT, version="v1.0")
        assert list_libraries_with_versions() == {"lib": ["v1.0"]}

    def test_web_url_ref_becomes_version_and_path(self, fake_source):
        add_library("lib", "https://github.com/example/example/tree/v2.0/docs")

        assert list_libraries_with_versions() == {"lib": ["v2.0"]}
        assert fake_source.calls[0]["docs_paths"] == ["docs"]
        assert (get_source("lib") or {})[
            "repo_url"
        ] == "https://github.com/example/example.git"

    def test_local_path_gets_dated_version(self, fake_source, tmp_path):
        result = add_library("lib", str(tmp_path))
        assert result.version.startswith("local-")

    def test_empty_extraction_errors_and_leaves_nothing(self, fake_source):
        fake_source.pages = {}
        with pytest.raises(ServiceError, match="no pages"):
            add_library("lib", SITEMAP)

        assert not get_library_raw_data_dir("lib", "latest").exists()
        assert get_source("lib") is None
        assert list_libraries_with_versions() == {}

    def test_stale_raw_files_without_db_rows_are_replaced(self, fake_source):
        raw = get_library_raw_data_dir("lib", "latest")
        raw.mkdir(parents=True)
        (raw / "stale.json").write_text('{"url": "https://example.com/stale"}')

        result = add_library("lib", SITEMAP)

        assert result.summary is None
        assert not (raw / "stale.json").exists()

    def test_missing_raw_files_do_not_duplicate_rows(self, fake_source):
        import shutil

        add_library("lib", SITEMAP)
        shutil.rmtree(get_library_raw_data_dir("lib", "latest"))

        add_library("lib", SITEMAP)

        from openground.query import get_library_stats

        assert (get_library_stats("lib", "latest") or {})["chunk_count"] == 2


class TestUpdateLibraries:
    def test_updates_every_stored_version(self, fake_source):
        add_library("lib", GIT, version="v1")
        add_library("lib", version="v2")
        fake_source.pages["extra"] = "More"

        results = update_libraries("lib")

        assert sorted(r.version for r in results) == ["v1", "v2"]
        assert all(r.summary and r.summary["added"] == 1 for r in results)

    def test_without_name_skips_libraries_without_source(self, fake_source):
        add_library("a", SITEMAP)
        add_library("b", SITEMAP)
        from openground.sources import remove_source

        remove_source("b")

        assert [r.library for r in update_libraries()] == ["a"]

    def test_errors_do_not_stop_the_batch(self, fake_source):
        add_library("a", SITEMAP)
        add_library("b", SITEMAP)
        fake_source.pages = {}

        results = update_libraries()

        assert len(results) == 2
        assert all("no pages" in (r.error or "") for r in results)

    def test_unknown_library_errors(self, fake_source):
        with pytest.raises(ServiceError, match="not found"):
            update_libraries("ghost")

    def test_library_without_source_errors(self, fake_source):
        add_library("lib", SITEMAP)
        from openground.sources import remove_source

        remove_source("lib")
        with pytest.raises(ServiceError, match="No remembered source"):
            update_libraries("lib")


class TestRemove:
    def test_resolve_single_version_automatically(self, fake_source):
        add_library("lib", GIT, version="v1")
        assert resolve_version("lib") == "v1"

    def test_resolve_multiple_versions_requires_choice(self, fake_source):
        add_library("lib", GIT, version="v1")
        add_library("lib", version="v2")

        with pytest.raises(ServiceError, match="v1, v2"):
            resolve_version("lib")
        assert resolve_version("lib", "v2") == "v2"

    def test_resolve_unknown_library_or_version(self, fake_source):
        add_library("lib", SITEMAP)
        with pytest.raises(ServiceError, match="'ghost' not found"):
            resolve_version("ghost")
        with pytest.raises(ServiceError, match="Version 'v9'"):
            resolve_version("lib", "v9")

    def test_remove_deletes_rows_files_and_last_source(self, fake_source):
        add_library("lib", SITEMAP)

        remove_library("lib", "latest")

        assert not library_version_exists("lib", "latest")
        assert not get_library_raw_data_dir("lib", "latest").exists()
        assert get_source("lib") is None

    def test_remove_keeps_source_while_versions_remain(self, fake_source):
        add_library("lib", GIT, version="v1")
        add_library("lib", version="v2")

        remove_library("lib", "v1")

        assert list_libraries_with_versions() == {"lib": ["v2"]}
        assert get_source("lib") is not None


def test_list_libraries_reports_remembered_sources(fake_source):
    add_library("lib", SITEMAP)
    assert list_libraries() == [("lib", ["latest"], True)]


def test_reset_data_deletes_everything(fake_source):
    add_library("lib", SITEMAP)
    reset_data()

    assert not get_data_home().exists()
    assert list_libraries_with_versions() == {}
