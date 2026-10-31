import json

import pytest
from typer.testing import CliRunner

from openground.cli import app
from openground.config import get_config_path, get_data_home
from openground.query import list_libraries_with_versions
from openground.sources import get_source
from openground.tests.test_config import write_config

runner = CliRunner()

GIT = "https://github.com/example/example.git"
SITEMAP = "https://docs.example.com/sitemap.xml"


def invoke(*args, input=None):
    return runner.invoke(app, list(args), input=input)


def test_help_lists_the_command_surface():
    result = invoke("--help")
    assert result.exit_code == 0
    for command in (
        "add",
        "update",
        "ls",
        "rm",
        "search",
        "serve",
        "install-mcp",
        "config",
        "stats",
        "reset",
    ):
        assert command in result.output


def test_version_flag():
    result = invoke("--version")
    assert result.exit_code == 0
    assert result.output.strip()


@pytest.mark.parametrize(
    "command",
    ["nuke", "extract-git", "embed", "query", "list-libraries", "remove", "version"],
)
def test_removed_commands_are_gone(command):
    assert invoke(command).exit_code == 2


class TestAdd:
    def test_add_remembers_source_and_lists_library(self, fake_source):
        result = invoke("add", "lib", SITEMAP)

        assert result.exit_code == 0, result.output
        assert "Added lib (latest): 2 pages" in result.output
        assert (get_source("lib") or {})["sitemap_url"] == SITEMAP
        assert list_libraries_with_versions() == {"lib": ["latest"]}

    def test_add_git_options_reach_the_extractor(self, fake_source):
        result = invoke("add", "lib", GIT, "-d", "docs", "-d", "wiki", "-v", "v1.0")

        assert result.exit_code == 0, result.output
        assert fake_source.calls[0]["docs_paths"] == ["docs", "wiki"]
        assert list_libraries_with_versions() == {"lib": ["v1.0"]}

    def test_add_sitemap_filters_reach_the_extractor(self, fake_source):
        invoke("add", "lib", SITEMAP, "-f", "guide", "-f", "api")
        assert fake_source.calls[0]["filter_keywords"] == ["guide", "api"]

    def test_add_local_directory(self, fake_source, tmp_path):
        result = invoke("add", "lib", str(tmp_path))

        assert result.exit_code == 0, result.output
        assert (get_source("lib") or {})["local_path"] == str(tmp_path.resolve())

    def test_add_again_updates(self, fake_source):
        invoke("add", "lib", SITEMAP)
        fake_source.pages["guide"] = "Changed"

        result = invoke("add", "lib")

        assert result.exit_code == 0, result.output
        assert (
            "Updated lib (latest): 0 added, 1 modified, 0 deleted, 1 unchanged"
            in result.output
        )

    def test_add_without_source_or_memory_fails(self, fake_source):
        result = invoke("add", "lib")
        assert result.exit_code == 1
        assert "No remembered source" in result.output

    def test_add_version_on_sitemap_fails(self, fake_source):
        result = invoke("add", "lib", SITEMAP, "-v", "v2")
        assert result.exit_code == 1
        assert "--version" in result.output

    def test_add_unrecognized_source_fails(self, fake_source):
        result = invoke("add", "lib", "not-a-source")
        assert result.exit_code == 1


class TestUpdate:
    def test_update_named_library(self, fake_source):
        invoke("add", "lib", SITEMAP)
        fake_source.pages["extra"] = "More"

        result = invoke("update", "lib")

        assert result.exit_code == 0, result.output
        assert "Updated lib (latest): 1 added" in result.output

    def test_update_all(self, fake_source):
        invoke("add", "a", SITEMAP)
        invoke("add", "b", SITEMAP)

        result = invoke("update")

        assert result.exit_code == 0, result.output
        assert "a (latest) is up to date" in result.output
        assert "b (latest) is up to date" in result.output

    def test_update_with_nothing_stored(self, fake_source):
        result = invoke("update")
        assert result.exit_code == 0
        assert "No libraries with a remembered source" in result.output

    def test_update_unknown_library_fails(self, fake_source):
        assert invoke("update", "ghost").exit_code == 1

    def test_update_failure_exits_nonzero(self, fake_source):
        invoke("add", "lib", SITEMAP)
        fake_source.pages = {}

        result = invoke("update")

        assert result.exit_code == 1
        assert "lib (latest)" in result.output


class TestLs:
    def test_empty(self, fake_embeddings):
        result = invoke("ls")
        assert result.exit_code == 0
        assert "No libraries found" in result.output

    def test_lists_versions_and_source_flag(self, fake_source):
        invoke("add", "lib", GIT, "-v", "v1")
        invoke("add", "lib", "-v", "v2")
        invoke("add", "other", SITEMAP)

        result = invoke("ls")

        assert result.exit_code == 0
        assert "lib" in result.output and "v1, v2" in result.output
        assert "other" in result.output and "latest" in result.output
        assert "yes" in result.output


class TestRm:
    def test_auto_detects_the_only_version(self, fake_source):
        invoke("add", "lib", GIT, "-v", "v1")

        result = invoke("rm", "lib", "-y")

        assert result.exit_code == 0, result.output
        assert "Removed lib (v1)" in result.output
        assert list_libraries_with_versions() == {}
        assert get_source("lib") is None

    def test_multiple_versions_exit_1_and_list_them(self, fake_source):
        invoke("add", "lib", GIT, "-v", "v1")
        invoke("add", "lib", "-v", "v2")

        result = invoke("rm", "lib", "-y")

        assert result.exit_code == 1
        assert "v1, v2" in result.output
        assert list_libraries_with_versions() == {"lib": ["v1", "v2"]}

    def test_explicit_version(self, fake_source):
        invoke("add", "lib", GIT, "-v", "v1")
        invoke("add", "lib", "-v", "v2")

        result = invoke("rm", "lib", "-v", "v1", "-y")

        assert result.exit_code == 0, result.output
        assert list_libraries_with_versions() == {"lib": ["v2"]}

    def test_unknown_library_exits_1(self, fake_source):
        result = invoke("rm", "ghost", "-y")
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_unknown_version_exits_1(self, fake_source):
        invoke("add", "lib", SITEMAP)
        assert invoke("rm", "lib", "-v", "v9", "-y").exit_code == 1

    def test_confirmation_can_abort(self, fake_source):
        invoke("add", "lib", SITEMAP)

        result = invoke("rm", "lib", input="n\n")

        assert result.exit_code == 1
        assert list_libraries_with_versions() == {"lib": ["latest"]}

    def test_confirmation_accepts(self, fake_source):
        invoke("add", "lib", SITEMAP)
        result = invoke("rm", "lib", input="y\n")
        assert result.exit_code == 0
        assert list_libraries_with_versions() == {}


class TestSearch:
    def test_search_prints_matches(self, fake_source):
        invoke("add", "lib", SITEMAP)

        result = invoke("search", "guide", "-l", "lib", "-v", "latest", "-k", "1")

        assert result.exit_code == 0, result.output
        assert "Found 1 match" in result.output

    def test_search_without_filters(self, fake_source):
        invoke("add", "lib", SITEMAP)
        result = invoke("search", "intro")
        assert result.exit_code == 0, result.output
        assert "Found" in result.output

    def test_search_empty_database(self, fake_embeddings):
        result = invoke("search", "anything")
        assert "Found 0 matches" in result.output

    def test_unknown_library_lists_available(self, fake_source):
        invoke("add", "lib", SITEMAP)

        result = invoke("search", "guide", "-l", "typo")

        assert result.exit_code == 1
        assert "'typo' not found. Available libraries: lib" in result.output

    def test_unknown_version_lists_available(self, fake_source):
        invoke("add", "lib", SITEMAP)

        result = invoke("search", "guide", "-l", "lib", "-v", "v9")

        assert result.exit_code == 1
        assert "Available versions: latest" in result.output

    def test_version_filter_is_applied(self, fake_source):
        invoke("add", "lib", GIT, "-v", "v1")
        invoke("add", "lib", "-v", "v2")

        result = invoke("search", "page", "-l", "lib", "-v", "v1")

        assert "Version: v1" in result.output and "Version: v2" not in result.output

    def test_embedding_mismatch_exits_1(self, fake_source):
        invoke("add", "lib", SITEMAP)
        write_config({"embedding_backend": "fastembed"})

        result = invoke("search", "guide")

        assert result.exit_code == 1
        assert "openground reset" in result.output


class TestConfig:
    def test_shows_defaults_and_locations(self):
        result = invoke("config")

        assert result.exit_code == 0
        assert str(get_config_path()) in result.output
        assert "not created" in result.output
        assert (
            json.loads(
                result.output[result.output.index("{") : result.output.index("}") + 1]
            )["top_k"]
            == 5
        )
        assert str(get_data_home()) in result.output

    def test_shows_user_overrides(self):
        get_config_path().parent.mkdir(parents=True, exist_ok=True)
        get_config_path().write_text('{"top_k": 9}')

        result = invoke("config")

        assert '"top_k": 9' in result.output
        assert "not created" not in result.output

    def test_invalid_config_exits_1_but_still_shows_path(self):
        get_config_path().parent.mkdir(parents=True, exist_ok=True)
        get_config_path().write_text("{nope")

        result = invoke("config")

        assert result.exit_code == 1
        assert f"Config file: {get_config_path()}" in result.output
        assert "Invalid config file" in result.output

    def test_legacy_config_explains_the_change(self):
        get_config_path().parent.mkdir(parents=True, exist_ok=True)
        get_config_path().write_text('{"embeddings": {"batch_size": 8}}')

        result = invoke("config")

        assert result.exit_code == 1
        assert "flat keys" in result.output


class TestStats:
    def test_show_and_reset(self, fake_source):
        from openground.stats import increment_tool_call

        invoke("add", "lib", SITEMAP)
        increment_tool_call("search_documents_tool")

        shown = invoke("stats")
        assert "Libraries: 1" in shown.output
        assert "Chunks:    2" in shown.output
        assert "search_documents_tool: 1" in shown.output

        assert invoke("stats", "--reset").exit_code == 0
        assert "search_documents_tool: 0" in invoke("stats").output


def test_corrupt_stats_file_exits_1_and_reset_fixes_it(tmp_path):
    stats_file = get_data_home() / "stats.json"
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text("{bad")

    assert invoke("stats").exit_code == 1
    assert invoke("stats", "--reset").exit_code == 0
    assert invoke("stats").exit_code == 0


def test_corrupt_sources_file_exits_1(fake_source):
    from openground.config import get_sources_path

    get_sources_path().parent.mkdir(parents=True)
    get_sources_path().write_text("{bad")

    result = invoke("add", "lib", SITEMAP)

    assert result.exit_code == 1
    assert "Invalid sources file" in result.output


class TestReset:
    def test_reset_deletes_all_data(self, fake_source):
        invoke("add", "lib", SITEMAP)

        result = invoke("reset", "-y")

        assert result.exit_code == 0, result.output
        assert not get_data_home().exists()

    def test_reset_keeps_remembered_sources(self, fake_source):
        invoke("add", "lib", SITEMAP)
        invoke("reset", "-y")
        assert get_source("lib") is not None

    def test_reset_asks_for_confirmation(self, fake_source):
        invoke("add", "lib", SITEMAP)

        result = invoke("reset", input="n\n")

        assert result.exit_code == 1
        assert list_libraries_with_versions() == {"lib": ["latest"]}


def test_serve_reports_invalid_config_without_traceback():
    get_config_path().parent.mkdir(parents=True, exist_ok=True)
    get_config_path().write_text("{nope")

    result = invoke("serve")

    assert result.exit_code == 1
    assert "Invalid config file" in result.output


def test_serve_runs_the_mcp_server(monkeypatch):
    called = []
    monkeypatch.setattr("openground.server.run_server", lambda: called.append(True))

    assert invoke("serve").exit_code == 0
    assert called
