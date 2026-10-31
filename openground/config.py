import json
import os
from pathlib import Path
from typing import Literal

from openground.console import UserError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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
    """Remembered library sources, stored next to the config file."""
    return get_config_path().parent / "sources.json"


class Settings(BaseModel):
    """User-tunable settings. Stored as flat JSON at get_config_path()."""

    model_config = ConfigDict(extra="forbid")

    embedding_backend: Literal["fastembed", "sentence-transformers"] = (
        "sentence-transformers"
    )
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = Field(0, ge=0)
    batch_size: int = Field(32, gt=0)
    chunk_size: int = Field(800, gt=0)
    chunk_overlap: int = Field(200, ge=0)
    top_k: int = Field(5, gt=0)

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
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
LEGACY_KEYS = {
    "embeddings",
    "query",
    "extraction",
    "sources",
    "ingestion",
    "db_path",
    "table_name",
    "raw_data_dir",
}


def get_settings() -> Settings:
    """Load settings from the config file (cached for the process)."""
    global _settings_cache
    if _settings_cache is None:
        path = get_config_path()
        try:
            text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
            data = json.loads(text) if text else {}
            if isinstance(data, dict) and (legacy := LEGACY_KEYS & set(data)):
                problem = (
                    f"the config format changed to flat keys (found {', '.join(sorted(legacy))}). "
                    "Delete the file or see the README for the new format"
                )
            else:
                _settings_cache = Settings.model_validate(data)
                return _settings_cache
        except json.JSONDecodeError as e:
            problem = f"invalid JSON ({e})"
        except ValidationError as e:
            problem = "; ".join(
                f"{'.'.join(map(str, err['loc'])) or 'config'}: {err['msg']}"
                for err in e.errors()
            )
        raise UserError(
            f"Invalid config file {path}: {problem}\n"
            "Fix it or delete the file to reset to defaults."
        )
    return _settings_cache


def get_library_raw_data_dir(library_name: str, version: str) -> Path:
    return get_settings().raw_data_dir / library_name.lower() / version
