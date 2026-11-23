"""Register the openground MCP server with agent clients."""

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path

from openground.console import UserError, hint, success, warning


class Client(str, Enum):
    claude_code = "claude-code"
    cursor = "cursor"
    opencode = "opencode"


class InstallError(UserError):
    pass


def server_command(wsl: bool = False) -> list[str]:
    if wsl:
        return ["wsl.exe", "openground-mcp"]
    found = shutil.which("openground-mcp")
    return [str(Path(found).resolve()) if found else "openground-mcp"]


def _mcp_servers_entry(command: list[str]) -> dict:
    entry: dict = {"command": command[0]}
    if len(command) > 1:
        entry["args"] = command[1:]
    return entry


def mcp_config_json(wsl: bool = False) -> str:
    config = {"mcpServers": {"openground": _mcp_servers_entry(server_command(wsl))}}
    return json.dumps(config, indent=2)


def _merge_into_json_file(path: Path, key: str, entry: dict) -> None:
    """Add the openground entry under `key`, backing up and atomically rewriting the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}

    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as e:
            raise InstallError(
                f"{path} contains invalid JSON ({e}). Fix or delete it and retry."
            ) from e
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.name}.backup.{timestamp}")
        shutil.copy2(path, backup)
        print(f"Created backup: {backup}")

    servers = config.setdefault(key, {})
    if "openground" in servers:
        warning("'openground' is already configured; updating it.")
    servers["openground"] = entry

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as tmp:
            json.dump(config, tmp, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except OSError as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise InstallError(f"Could not write {path}: {e}") from e


def _install_claude_code(command: list[str]) -> None:
    claude = ["claude", "mcp"]
    try:
        subprocess.run(
            [*claude, "remove", "openground", "--scope", "user"], capture_output=True
        )
        result = subprocess.run(
            [
                *claude,
                "add",
                "--transport",
                "stdio",
                "--scope",
                "user",
                "openground",
                "--",
                *command,
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise InstallError(
            "'claude' CLI not found in PATH. Install Claude Code, or run "
            "`openground install-mcp` to print the config instead."
        ) from None
    if result.returncode != 0:
        raise InstallError(
            f"claude mcp add failed: {(result.stderr or result.stdout).strip()}"
        )


def _install_cursor(command: list[str]) -> None:
    path = Path.home() / ".cursor" / "mcp.json"
    _merge_into_json_file(path, "mcpServers", _mcp_servers_entry(command))


def _install_opencode(command: list[str]) -> None:
    path = Path.home() / ".config" / "opencode" / "opencode.json"
    entry = {"type": "local", "command": command, "enabled": True}
    _merge_into_json_file(path, "mcp", entry)


def install_to(client: Client, wsl: bool = False) -> None:
    installer = {
        Client.claude_code: _install_claude_code,
        Client.cursor: _install_cursor,
        Client.opencode: _install_opencode,
    }[client]
    installer(server_command(wsl))
    success(f"Installed openground to {client.value}.")
    if client is not Client.claude_code:
        hint(f"Restart {client.value} to apply changes.")
