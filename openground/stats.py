import json
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar, TypedDict

from openground.config import DEFAULT_DB_PATH, DEFAULT_TABLE_NAME, get_data_home
from openground.query import _get_table, list_libraries_with_versions

F = TypeVar("F", bound=Callable[..., Any])


class StatsJson(TypedDict):
    tool_calls: dict[str, int]
    libraries_count: int
    total_chunks: int


def get_stats_path() -> Path:
    """Get the path to the stats file.

    Returns:
        Path to stats.json in the data home directory.
    """
    return get_data_home() / "stats.json"


def get_default_stats() -> StatsJson:
    """Get the default statistics structure.

    Returns:
        StatsJson with default stats, all tool call counts initialized to 0.
    """
    return StatsJson(
        tool_calls={
            "search_documents_tool": 0,
            "list_libraries_tool": 0,
            "get_full_content_tool": 0,
        },
        libraries_count=0,
        total_chunks=0,
    )


def load_stats(
    db_path: Path | None = None, table_name: str | None = None
) -> StatsJson:
    """Load statistics from the stats file.

    Args:
        db_path: Optional path to LanceDB storage for computing libraries_count and total_chunks.
        table_name: Optional table name for computing libraries_count and total_chunks.

    Returns:
        StatsJson with loaded stats. Computed fields are calculated if db_path/table_name provided.

    Raises ValueError if file contains invalid JSON.
    """
    stats_path = get_stats_path()

    default = get_default_stats()

    if not stats_path.exists():
        stats = default.copy()
    else:
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    stats = default.copy()
                else:
                    loaded = json.loads(content)

                    if "tool_calls" not in loaded:
                        stats = default.copy()
                    else:
                        tool_calls = loaded["tool_calls"].copy()
                        for tool_name in default["tool_calls"]:
                            if tool_name not in tool_calls:
                                tool_calls[tool_name] = 0

                        stats = StatsJson(
                            tool_calls=tool_calls,
                            libraries_count=0,
                            total_chunks=0,
                        )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in stats file {stats_path}: {e}") from e
        except Exception as e:
            raise ValueError(f"Error reading stats file {stats_path}: {e}") from e

    if db_path is not None and table_name is not None:
        stats["libraries_count"] = get_libraries_count(
            db_path=db_path, table_name=table_name
        )
        stats["total_chunks"] = get_total_chunks(db_path=db_path, table_name=table_name)

    return stats


def save_stats(stats: StatsJson) -> None:
    """Save statistics to the stats file atomically.

    Only saves tool_calls to JSON; computed fields (libraries_count, total_chunks) are not persisted.

    Args:
        stats: StatsJson to save. Only tool_calls will be written to file.

    Creates the stats directory if it doesn't exist.
    """
    stats_path = get_stats_path()
    stats_path.parent.mkdir(parents=True, exist_ok=True)

    save_data = {"tool_calls": stats["tool_calls"]}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=stats_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp_file:
            json.dump(save_data, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)

        tmp_path.replace(stats_path)
    except Exception:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise


def increment_tool_call(tool_name: str) -> None:
    """Increment the call count for a tool.

    Args:
        tool_name: Name of the tool to increment.
    """
    stats = load_stats()
    if "tool_calls" not in stats:
        stats["tool_calls"] = {}
    if tool_name not in stats["tool_calls"]:
        stats["tool_calls"][tool_name] = 0
    stats["tool_calls"][tool_name] += 1
    save_stats(stats)


def get_libraries_count(
    db_path: Path = DEFAULT_DB_PATH, table_name: str = DEFAULT_TABLE_NAME
) -> int:
    """Count the number of unique libraries in the database.

    Args:
        db_path: Path to LanceDB storage.
        table_name: Table name to query.

    Returns:
        Number of unique libraries. Returns 0 if table doesn't exist.
    """
    libraries = list_libraries_with_versions(db_path=db_path, table_name=table_name)
    return len(libraries)


def get_total_chunks(
    db_path: Path = DEFAULT_DB_PATH, table_name: str = DEFAULT_TABLE_NAME
) -> int:
    """Count the total number of chunks in the database.

    Args:
        db_path: Path to LanceDB storage.
        table_name: Table name to query.

    Returns:
        Total number of chunks. Returns 0 if table doesn't exist.
    """
    table = _get_table(db_path, table_name)
    if table is None:
        return 0
    return table.count_rows()


def reset_stats() -> None:
    """Reset tool call counts to their default values (all zeros)."""
    stats = load_stats()
    default = get_default_stats()
    stats["tool_calls"] = default["tool_calls"].copy()
    stats["libraries_count"] = default["libraries_count"]
    stats["total_chunks"] = default["total_chunks"]
    save_stats(stats)

