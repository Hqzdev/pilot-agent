from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from pilot_agent.agent.phases import PHASES
from pilot_agent.backends.local import LocalBackend
from pilot_agent.cli import app
from pilot_agent.config.credentials import get_credential
from pilot_agent.config.schema import load_config
from pilot_agent.tools.web_fetch import WebFetchTool


def test_local_backend_exec_and_blocklist(tmp_path: Path) -> None:
    backend = LocalBackend()

    result = backend.exec("pwd", str(tmp_path), timeout_s=10)

    assert result.exit_code == 0
    assert str(tmp_path) in result.output
    with pytest.raises(ValueError, match="blocked dangerous command"):
        backend.exec("sudo whoami", str(tmp_path), timeout_s=10)


def test_backend_tools_settings_and_auth_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    runner = CliRunner()

    backend = runner.invoke(app, ["backend", "local"])
    tools = runner.invoke(app, ["tools", "web_fetch", "--enable"])
    auth = runner.invoke(app, ["auth", "set", "tavily", "tvly-test"])
    settings = runner.invoke(app, ["settings"])
    cfg = load_config(home=home, project_root=tmp_path / "project")

    assert backend.exit_code == 0
    assert tools.exit_code == 0
    assert auth.exit_code == 0
    assert settings.exit_code == 0
    assert cfg.backend == "local"
    assert cfg.tools.web_fetch.enabled is True
    assert get_credential("tavily", home) == "tvly-test"
    assert "web_search" in settings.output


def test_web_fetch_blocks_private_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    tool = WebFetchTool()

    with pytest.raises(ValueError, match="blocked private"):
        tool.execute(url="http://metadata.internal/")


def test_web_tools_phase_matrix() -> None:
    assert "web_search" in PHASES["discovery"].tools
    assert "web_search" in PHASES["planning"].tools
    assert "web_fetch" in PHASES["planning"].tools
    assert "web_search" in PHASES["coding"].tools
    assert "web_fetch" in PHASES["coding"].tools
    assert "web_search" not in PHASES["deploy"].tools
    assert "web_fetch" not in PHASES["deploy"].tools
    assert "web_search" not in PHASES["marketing"].tools
    assert "web_fetch" not in PHASES["marketing"].tools


def test_credentials_file_does_not_touch_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    runner = CliRunner()

    result = runner.invoke(app, ["auth", "set", "brave", "brave-secret"])

    assert result.exit_code == 0
    assert "brave-secret" in (home / "credentials.yaml").read_text(encoding="utf-8")
    config_path = home / "config.yaml"
    if config_path.exists():
        assert "brave-secret" not in config_path.read_text(encoding="utf-8")
    data = yaml.safe_load((home / "credentials.yaml").read_text(encoding="utf-8"))
    assert data["brave"]["api_key"] == "brave-secret"
