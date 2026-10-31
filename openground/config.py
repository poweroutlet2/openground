import json
import os
from pathlib import Path
from typing import Literal

from openground.console import UserError
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

TABLE_NAME = "documents"

# Known embedding models and their vector dimensions. Used to size the LanceDB schema.
MODEL_DIMENSIONS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-m3": 1024,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
}


def get_data_home() -> Path:
    """Base directory for openground data (db, raw files, stats)."""
    if xdg_data := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data).expanduser() / "openground"

    if os.name == "nt":  # Windows
        return Path.home() / "AppData" / "Local" / "openground"
    return Path.home() / ".local" / "share" / "openground"


def get_config_path() -> Path:
    """Path to the optional user config file."""
    if xdg_config := os.environ.get("XDG_CONFIG_HOME"):
        config_dir = Path(xdg_config).expanduser() / "openground"
    elif os.name == "nt":  # Windows
        config_dir = Path.home() / "AppData" / "Local" / "openground"
    else:
        config_dir = Path.home() / ".config" / "openground"

    return config_dir / "config.json"


def get_sources_path() -> Path:
    """Path to the user sources registry (the only sources file)."""
    return Path.home() / ".openground" / "sources.json"


class Settings(BaseModel):
    """User-tunable settings. Stored as flat JSON at get_config_path()."""

    model_config = ConfigDict(extra="forbid")

    embedding_backend: Literal["fastembed", "sentence-transformers"] = (
        "sentence-transformers"
    )
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 0
    batch_size: int = 32
    chunk_size: int = 800
    chunk_overlap: int = 200
    top_k: int = 5

    @model_validator(mode="after")
    def _default_dimensions(self) -> "Settings":
        if not self.embedding_dimensions:
            if self.embedding_model not in MODEL_DIMENSIONS:
                raise ValueError(
                    f"unknown embedding_model {self.embedding_model!r}: "
                    "set embedding_dimensions too"
                )
            self.embedding_dimensions = MODEL_DIMENSIONS[self.embedding_model]
        return self

    @property
    def db_path(self) -> Path:
        return get_data_home() / "lancedb"

    @property
    def raw_data_dir(self) -> Path:
        return get_data_home() / "raw_data"


_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Load settings from the config file (cached for the process)."""
    global _settings_cache
    if _settings_cache is None:
        path = get_config_path()
        try:
            text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
            _settings_cache = Settings.model_validate(json.loads(text) if text else {})
        except json.JSONDecodeError as e:
            problem = f"invalid JSON ({e})"
        except ValidationError as e:
            problem = "; ".join(
                f"{'.'.join(map(str, err['loc'])) or 'config'}: {err['msg']}"
                for err in e.errors()
            )
        else:
            return _settings_cache
        raise UserError(
            f"Invalid config file {path}: {problem}\n"
            "Fix it or delete the file to reset to defaults."
        )
    return _settings_cache


def clear_settings_cache() -> None:
    global _settings_cache
    _settings_cache = None


def get_library_raw_data_dir(library_name: str, version: str) -> Path:
    return get_settings().raw_data_dir / library_name.lower() / version
