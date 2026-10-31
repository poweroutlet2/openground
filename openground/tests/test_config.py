import json

import pytest

import openground.config as config
from openground.config import (
    get_config_path,
    get_library_raw_data_dir,
    get_settings,
)
from openground.console import UserError


def write_config(data) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    config._settings_cache = None


def test_defaults_without_config_file():
    settings = get_settings()
    assert settings.embedding_backend == "sentence-transformers"
    assert settings.embedding_dimensions == 384
    assert settings.top_k == 5
    assert not get_config_path().exists()


def test_paths_are_derived_from_data_home(tmp_path):
    assert config.get_db_path() == tmp_path / "data" / "openground" / "lancedb"
    assert config.get_raw_data_dir() == tmp_path / "data" / "openground" / "raw_data"
    assert (
        get_library_raw_data_dir("MyLib", "v1")
        == config.get_raw_data_dir() / "mylib" / "v1"
    )


def test_user_values_override_defaults():
    write_config({"chunk_size": 500, "top_k": 3})
    settings = get_settings()
    assert (settings.chunk_size, settings.top_k) == (500, 3)
    assert settings.chunk_overlap == 200


def test_known_model_sets_dimensions():
    write_config({"embedding_model": "BAAI/bge-base-en-v1.5"})
    assert get_settings().embedding_dimensions == 768


def test_unknown_model_requires_dimensions():
    write_config({"embedding_model": "acme/custom"})
    with pytest.raises(UserError, match="embedding_dimensions"):
        get_settings()

    write_config({"embedding_model": "acme/custom", "embedding_dimensions": 64})
    assert get_settings().embedding_dimensions == 64


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        {"chunk_sze": 1},
        {"embeddings": {"batch_size": 1}},
        {"top_k": "many"},
    ],
)
def test_invalid_config_raises_user_error(content):
    write_config(content)
    with pytest.raises(UserError, match="Invalid config file"):
        get_settings()


def test_empty_config_file_uses_defaults():
    write_config("")
    assert get_settings().top_k == 5


@pytest.mark.parametrize(
    "legacy",
    [
        {"embeddings": {"batch_size": 1}},
        {"db_path": "/x"},
        {"table_name": "t"},
        {"sources": {}},
    ],
)
def test_legacy_config_gets_actionable_message(legacy):
    write_config(legacy)
    with pytest.raises(UserError, match="format changed to flat keys"):
        get_settings()


def test_sources_path_sits_next_to_config():
    assert config.get_sources_path() == get_config_path().parent / "sources.json"


def test_explicit_dimensions_must_match_a_known_model():
    write_config(
        {"embedding_model": "BAAI/bge-base-en-v1.5", "embedding_dimensions": 384}
    )
    with pytest.raises(UserError, match="768-dimensional"):
        get_settings()

    write_config(
        {"embedding_model": "BAAI/bge-base-en-v1.5", "embedding_dimensions": 768}
    )
    assert get_settings().embedding_dimensions == 768


def test_zero_overlap_is_allowed():
    write_config({"chunk_overlap": 0})
    assert get_settings().chunk_overlap == 0
