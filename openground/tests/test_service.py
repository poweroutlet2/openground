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
from openground.console import UserError
from openground.sources import get_source
from openground.tests.test_config import write_config

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

    @pytest.mark.parametrize(
        "source, option, flag",
        [
            (SITEMAP, {"version": "v2"}, "--version"),
            ("LOCAL", {"version": "v2"}, "--version"),
            (SITEMAP, {"docs_paths": ["docs"]}, "--docs-path"),
            ("LOCAL", {"docs_paths": ["docs"]}, "--docs-path"),
            (GIT, {"filter_keywords": ["x"]}, "--filter"),
            ("LOCAL", {"filter_keywords": ["x"]}, "--filter"),
        ],
    )
    def test_options_that_do_not_apply_are_rejected(
        self, fake_source, tmp_path, source, option, flag
    ):
        source = str(tmp_path) if source == "LOCAL" else source
        with pytest.raises(ServiceError, match=f"{flag} only applies to"):
            add_library("lib", source, **option)
        assert get_source("lib") is None

    def test_inapplicable_option_is_rejected_for_remembered_source(self, fake_source):
        add_library("lib", SITEMAP)
        with pytest.raises(ServiceError, match="--docs-path"):
            add_library("lib", docs_paths=["docs"])

    def test_explicit_latest_version_is_fine_for_any_source(self, fake_source):
        assert add_library("lib", SITEMAP, version="latest").version == "latest"

    def test_git_version_alias_is_canonicalized(self, fake_source):
        fake_source.refs["1.0"] = "v1.0"

        first = add_library("g", GIT, version="1.0")
        again = add_library("g", GIT, version="1.0")

        assert first.version == "v1.0"
        assert again.summary is not None
        assert list_libraries_with_versions() == {"g": ["v1.0"]}
        assert get_library_raw_data_dir("g", "v1.0").exists()
        assert not get_library_raw_data_dir("g", "1.0").exists()
        assert fake_source.calls[0]["version"] == "v1.0"
        assert resolve_version("g", "v1.0") == "v1.0"

    def test_missing_git_ref_errors_before_extracting(self, fake_source):
        fake_source.refs["nope"] = None
        with pytest.raises(ServiceError, match="'nope' not found"):
            add_library("g", GIT, version="nope")
        assert fake_source.calls == []

    def test_embedding_mismatch_errors_before_extracting(self, fake_source):
        add_library("lib", SITEMAP)
        write_config({"embedding_backend": "fastembed"})
        fake_source.calls.clear()

        with pytest.raises(UserError, match="openground reset"):
            add_library("lib", SITEMAP)
        assert fake_source.calls == []
        assert update_libraries()[0].error

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

    def test_local_path_uses_latest_version(self, fake_source, tmp_path):
        assert add_library("lib", str(tmp_path)).version == "latest"

    def test_local_path_must_be_a_directory(self, fake_source, tmp_path):
        with pytest.raises(ServiceError, match="Not a directory"):
            add_library("lib", str(tmp_path / "missing"))
        file = tmp_path / "f.md"
        file.write_text("x")
        with pytest.raises(ServiceError, match="Not a directory"):
            add_library("lib", str(file))

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


def test_reset_deletes_only_owned_paths(fake_source):
    from openground.config import get_config_path, get_db_path, get_raw_data_dir
    from openground.stats import get_stats_path, increment_tool_call

    add_library("lib", SITEMAP)
    increment_tool_call("search_documents_tool")
    # config shares the data dir on some platforms
    stray = get_data_home() / "config.json"
    stray.write_text("{}")
    get_config_path().parent.mkdir(parents=True, exist_ok=True)
    get_config_path().write_text("{}")

    reset_data()

    assert not get_db_path().exists()
    assert not get_raw_data_dir().exists()
    assert not get_stats_path().exists()
    assert stray.exists() and get_config_path().exists()
    assert get_source("lib") is not None
    assert list_libraries_with_versions() == {}


class TestOneSourcePerLibrary:
    def test_different_source_while_versions_stored_errors(self, fake_source):
        add_library("lib", GIT, version="v1")

        with pytest.raises(
            ServiceError, match="already uses .*example.git.*openground rm lib"
        ):
            add_library("lib", "https://github.com/other/repo.git", version="v2")
        assert list_libraries_with_versions() == {"lib": ["v1"]}

    def test_same_source_in_any_spelling_is_fine(self, fake_source):
        add_library("lib", GIT, version="v1")
        add_library("lib", "https://github.com/example/example", version="v2")
        add_library("lib", "https://github.com/example/example/tree/v3/docs")

        assert list_libraries_with_versions() == {"lib": ["v1", "v2", "v3"]}

    def test_source_can_change_after_everything_is_removed(self, fake_source):
        add_library("lib", GIT)
        remove_library("lib", "latest")

        add_library("lib", SITEMAP)

        assert get_source("lib")["type"] == "sitemap"

    def test_source_can_change_when_nothing_is_stored(self, fake_source):
        from openground.sources import save_source

        save_source("lib", {"type": "sitemap", "sitemap_url": SITEMAP})
        add_library("lib", GIT)
        assert get_source("lib")["type"] == "git_repo"


class TestAddWithoutSource:
    def test_second_latest_version_is_not_created_silently(self, fake_source):
        add_library("foo", GIT, version="v1")

        with pytest.raises(
            ServiceError, match=r"'foo' is already stored \(v1\).*update foo.*-v"
        ):
            add_library("foo")
        assert list_libraries_with_versions() == {"foo": ["v1"]}

    def test_explicit_version_adds_another(self, fake_source):
        add_library("foo", GIT, version="v1")
        add_library("foo", version="v2")
        assert list_libraries_with_versions() == {"foo": ["v1", "v2"]}

    def test_existing_latest_is_updated(self, fake_source):
        add_library("foo", GIT)
        assert add_library("foo").summary is not None


class TestSourcesFileValidation:
    @pytest.mark.parametrize(
        "content, problem",
        [
            ("[]", "top level"),
            ('{"lib": "x"}', "entry 'lib'"),
            ('{"lib": {"type": "ftp"}}', "entry 'lib'"),
            ('{"lib": {"type": "git_repo"}}', "missing 'repo_url'"),
            ('{"lib": {"type": "sitemap", "sitemap_url": 3}}', "missing 'sitemap_url'"),
            ('{"lib": {"type": "local_path"}}', "missing 'local_path'"),
            (
                '{"lib": {"type": "git_repo", "repo_url": "u", "docs_paths": "docs"}}',
                "'docs_paths' must be a list",
            ),
        ],
    )
    def test_bad_entries_are_named(self, fake_source, content, problem):
        from openground.config import get_sources_path

        get_sources_path().parent.mkdir(parents=True, exist_ok=True)
        get_sources_path().write_text(content)

        with pytest.raises(UserError, match=problem) as exc:
            add_library("other", SITEMAP)
        assert str(get_sources_path()) in str(exc.value)

    def test_bad_file_fails_before_any_extraction(self, fake_source):
        from openground.config import get_sources_path

        get_sources_path().parent.mkdir(parents=True, exist_ok=True)
        get_sources_path().write_text('{"lib": {"type": "git_repo"}}')

        with pytest.raises(UserError):
            add_library("other", SITEMAP)
        assert fake_source.calls == []
        assert list_libraries_with_versions() == {}


def test_unknown_home_directory_is_a_clean_error(fake_source):
    with pytest.raises(ServiceError, match="Could not resolve path"):
        add_library("lib", "~nosuchuser_xyz/docs")


def test_missing_git_binary_is_a_clean_error(monkeypatch):
    from openground.extract.git import get_default_branch, resolve_remote_ref

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("subprocess.run", no_git)

    for call in (
        lambda: resolve_remote_ref(GIT, "v1"),
        lambda: get_default_branch(GIT),
    ):
        with pytest.raises(UserError, match="git is not installed.*git-scm.com"):
            call()
