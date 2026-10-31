import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from openground.cli import app

runner = CliRunner()


def invoke(*args):
    return runner.invoke(app, ["install-mcp", *args])


def test_prints_json_by_default():
    result = invoke()

    assert result.exit_code == 0
    config = json.loads(
        result.output[result.output.index("{") : result.output.rindex("}") + 1]
    )
    assert "command" in config["mcpServers"]["openground"]
    assert "install-mcp claude-code" in result.output


def test_wsl_prints_wsl_wrapper():
    result = invoke("--wsl")

    config = json.loads(
        result.output[result.output.index("{") : result.output.rindex("}") + 1]
    )
    assert config["mcpServers"]["openground"] == {
        "command": "wsl.exe",
        "args": ["openground-mcp"],
    }


def test_unknown_client_is_rejected():
    assert invoke("vscode").exit_code == 2


class TestClaudeCode:
    def test_removes_existing_then_adds(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as run:
            result = invoke("claude-code")

        assert result.exit_code == 0
        assert [c[0][0] for c in run.call_args_list] == [
            ["claude", "mcp", "remove", "openground", "--scope", "user"],
            [
                "claude",
                "mcp",
                "add",
                "--transport",
                "stdio",
                "--scope",
                "user",
                "openground",
                "--",
                "openground-mcp",
            ],
        ]

    def test_wsl_wraps_the_server_command(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as run:
            invoke("claude-code", "--wsl")

        assert run.call_args_list[1][0][0][-2:] == ["wsl.exe", "openground-mcp"]

    def test_fresh_install_ignores_failed_remove(self):
        with patch(
            "subprocess.run",
            side_effect=[MagicMock(returncode=1), MagicMock(returncode=0)],
        ):
            assert invoke("claude-code").exit_code == 0

    def test_add_failure_exits_1(self):
        failed = MagicMock(returncode=1, stderr="boom", stdout="")
        with patch("subprocess.run", return_value=failed):
            result = invoke("claude-code")

        assert result.exit_code == 1
        assert "boom" in result.output

    def test_missing_claude_cli_exits_1(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = invoke("claude-code")

        assert result.exit_code == 1
        assert "'claude' CLI not found" in result.output


class TestJsonFileClients:
    def test_cursor_creates_config(self, tmp_path):
        result = invoke("cursor")

        assert result.exit_code == 0, result.output
        config = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
        assert "command" in config["mcpServers"]["openground"]

    def test_cursor_preserves_other_servers_and_backs_up(self, tmp_path):
        path = tmp_path / ".cursor" / "mcp.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))

        assert invoke("cursor").exit_code == 0

        servers = json.loads(path.read_text())["mcpServers"]
        assert servers["other"] == {"command": "x"}
        assert "openground" in servers
        assert len(list(path.parent.glob("mcp.json.backup.*"))) == 1

    def test_cursor_wsl(self, tmp_path):
        invoke("cursor", "--wsl")

        entry = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())[
            "mcpServers"
        ]["openground"]
        assert entry == {"command": "wsl.exe", "args": ["openground-mcp"]}

    def test_opencode_entry_shape(self, tmp_path):
        result = invoke("opencode")

        assert result.exit_code == 0, result.output
        config = json.loads(
            (tmp_path / ".config" / "opencode" / "opencode.json").read_text()
        )
        entry = config["mcp"]["openground"]
        assert entry["type"] == "local"
        assert entry["enabled"] is True
        assert isinstance(entry["command"], list)

    @pytest.mark.parametrize(
        "client, relpath",
        [
            ("cursor", ".cursor/mcp.json"),
            ("opencode", ".config/opencode/opencode.json"),
        ],
    )
    def test_invalid_json_exits_1_and_is_untouched(self, tmp_path, client, relpath):
        path = tmp_path / relpath
        path.parent.mkdir(parents=True)
        path.write_text("{broken")

        result = invoke(client)

        assert result.exit_code == 1
        assert "invalid JSON" in result.output
        assert path.read_text() == "{broken"
