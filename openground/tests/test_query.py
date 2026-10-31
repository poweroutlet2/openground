import pytest

from openground.console import UserError
from openground.query import (
    check_embedding_config,
    check_library_version,
    list_libraries_with_versions,
    search,
)
from openground.service import add_library
from openground.tests.test_config import write_config

GIT = "https://github.com/example/example.git"


@pytest.fixture
def two_versions(fake_source):
    add_library("lib", GIT, version="v1")
    add_library("lib", version="v2")
    add_library("other", GIT)


class TestSearchFilters:
    def test_library_and_version_filters_combine(self, two_versions):
        result = search("page", version="v1", library_name="lib")

        assert "Found 2 matches" in result
        assert "Version: v1" in result
        assert "Version: v2" not in result

    def test_version_only_filter(self, two_versions):
        result = search("page", version="v2")
        assert "Found 2 matches" in result and "Version: v1" not in result

    def test_library_only_filter(self, two_versions):
        result = search("page", library_name="other", top_k=10)
        assert "Found 2 matches" in result

    def test_top_k_limits_results(self, two_versions):
        assert "Found 1 match." in search("page", library_name="lib", top_k=1)

    def test_empty_database(self, fake_embeddings):
        assert search("anything") == "Found 0 matches."


class TestCheckLibraryVersion:
    def test_unknown_library_lists_available(self, two_versions):
        with pytest.raises(
            UserError, match="'typo' not found. Available libraries: lib, other"
        ):
            check_library_version("typo", None)

    def test_unknown_version_lists_available(self, two_versions):
        with pytest.raises(
            UserError,
            match="Version 'v9' not found for library 'lib'. Available versions: v1, v2",
        ):
            check_library_version("lib", "v9")

    def test_version_without_library_checks_all(self, two_versions):
        check_library_version(None, "v2")
        with pytest.raises(UserError, match="Version 'v9' not found"):
            check_library_version(None, "v9")

    def test_empty_database(self, fake_embeddings):
        with pytest.raises(UserError, match="none"):
            check_library_version("lib", None)

    def test_search_applies_the_check(self, two_versions):
        with pytest.raises(UserError, match="not found"):
            search("page", library_name="typo")


class TestEmbeddingConfig:
    def test_matching_config_passes(self, two_versions):
        check_embedding_config()

    def test_no_table_passes(self, fake_embeddings):
        check_embedding_config()

    @pytest.mark.parametrize(
        "override",
        [
            {"embedding_backend": "fastembed"},
            {"embedding_model": "BAAI/bge-base-en-v1.5"},
        ],
    )
    def test_mismatch_explains_how_to_fix(self, two_versions, override):
        write_config(override)

        with pytest.raises(UserError, match="openground reset") as exc:
            check_embedding_config()
        assert "config.json" in str(exc.value)

    def test_search_refuses_mismatched_model(self, two_versions):
        write_config({"embedding_backend": "fastembed"})
        with pytest.raises(UserError, match="mismatch"):
            search("page")


def test_new_libraries_are_visible_without_restart(fake_source):
    assert list_libraries_with_versions() == {}
    add_library("lib", GIT)
    assert list_libraries_with_versions() == {"lib": ["latest"]}
