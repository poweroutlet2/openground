import json
import os
from pathlib import Path
from typing import Literal

from openground.console import UserError, warning
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
    elif os.name == "nt":  # Windows: roaming, so it is separate from the data dir
        config_dir = Path.home() / "AppData" / "Roaming" / "openground"
    else:
        config_dir = Path.home() / ".config" / "openground"

    return config_dir / "config.json"


def get_sources_path() -> Path:
    """Remembered library sources, stored next to the config file."""
    return get_config_path().parent / "sources.json"


def get_db_path() -> Path:
    return get_data_home() / "lancedb"


def get_raw_data_dir() -> Path:
    return get_data_home() / "raw_data"


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
        known = MODEL_DIMENSIONS.get(self.embedding_model)
        if not self.embedding_dimensions:
            if known is None:
                raise ValueError(
                    f"unknown embedding_model {self.embedding_model!r}: "
                    "set embedding_dimensions too"
                )
            self.embedding_dimensions = known
        elif known and self.embedding_dimensions != known:
            raise ValueError(
                f"{self.embedding_model} produces {known}-dimensional vectors, "
                f"not {self.embedding_dimensions}: remove embedding_dimensions"
            )
        return self


_settings_cache: Settings | None = None
LEGACY_SECTIONS = {"embeddings", "query", "extraction", "sources", "ingestion"}
LEGACY_TOP_LEVEL = {"db_path", "table_name", "raw_data_dir"}


def _flatten_legacy(data: dict) -> dict:
    """Map a pre-0.15 nested config onto the flat keys, keeping only non-default values."""
    flat = {}
    for section in ("embeddings", "query"):
        if isinstance(data.get(section), dict):
            flat.update(data[section])
    flat = {k: v for k, v in flat.items() if k in Settings.model_fields}
    if (
        flat.get("embedding_model", Settings.model_fields["embedding_model"].default)
        in MODEL_DIMENSIONS
    ):
        flat.pop("embedding_dimensions", None)
    return {k: v for k, v in flat.items() if v != Settings.model_fields[k].default}


def _migrate_legacy_config(path: Path) -> None:
    """Rewrite a pre-0.15 config file in the flat format, keeping a .bak copy."""
    source = path
    if not path.exists() and os.name == "nt":
        source = get_data_home() / "config.json"  # pre-0.15 Windows location
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or not (
        LEGACY_SECTIONS & set(data) or LEGACY_TOP_LEVEL & set(data)
    ):
        return

    backup = source.with_name("config.json.bak")
    backup.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_flatten_legacy(data), indent=2), encoding="utf-8")
    if source != path:
        source.unlink()
    warning(f"Migrated config to the new flat format: {path} (old file: {backup})")
    current = {"db_path": get_db_path(), "raw_data_dir": get_raw_data_dir()}
    moved = [
        k
        for k, p in current.items()
        if k in data and Path(str(data[k])).expanduser() != p
    ]
    if moved:
        warning(
            f"  {', '.join(moved)} are no longer settings; openground now uses {get_data_home()}"
        )


def get_settings() -> Settings:
    """Load settings from the config file (cached for the process)."""
    global _settings_cache
    if _settings_cache is None:
        path = get_config_path()
        _migrate_legacy_config(path)
        try:
            text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
            _settings_cache = Settings.model_validate(json.loads(text) if text else {})
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
    return get_raw_data_dir() / library_name.lower() / version
