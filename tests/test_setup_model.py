from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from devagent.cli import app, setup_wizard
from devagent.config.schema import load_config


def test_setup_with_existing_env_key_writes_config_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVAGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    runner = CliRunner()

    result = runner.invoke(app, ["setup", "--provider", "anthropic"], input="\nn\n")

    assert result.exit_code == 0
    cfg_path = tmp_path / "home" / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    assert "test-secret" not in text
    data = yaml.safe_load(text)
    assert data["provider"] == "anthropic"
    assert data["api_key_env"] == "ANTHROPIC_API_KEY"
    assert data["phases"]["deploy"]["enabled"] is False


def test_setup_env_file_secret_has_0600_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DEVAGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["setup", "--provider", "anthropic"],
        input="secret-key\n2\n\nY\n",
    )

    env_path = tmp_path / "home" / ".env"
    assert result.exit_code == 0
    assert "secret-key" not in (tmp_path / "home" / "config.yaml").read_text(encoding="utf-8")
    assert "secret-key" in env_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_dotenv_is_loaded_for_api_key_presence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text("export ANTHROPIC_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cfg = load_config(home=home, project_root=tmp_path / "project")

    assert cfg.resolve_key() == "from-dotenv"


def test_model_direct_switch_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVAGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    switch = runner.invoke(app, ["model", "openrouter:qwen/qwen3-coder"])
    listing = runner.invoke(app, ["model", "--list"])
    cfg = load_config(home=tmp_path / "home", project_root=tmp_path / "project")

    assert switch.exit_code == 0
    assert "openrouter:qwen/qwen3-coder" in switch.output
    assert cfg.provider == "openrouter"
    assert cfg.model == "qwen/qwen3-coder"
    assert cfg.api_key_env == "OPENROUTER_API_KEY"
    assert listing.exit_code == 0
    assert "qwen/qwen3-coder" in listing.output


def test_model_invalid_provider_is_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVAGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    result = runner.invoke(app, ["model", "bad:model"])

    assert result.exit_code == 1
    assert "Run: devagent setup" in result.output


def test_setup_wizard_can_be_called_directly_with_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(setup_wizard.Prompt, "ask", lambda *args, **kwargs: kwargs["default"])
    monkeypatch.setattr(setup_wizard.Confirm, "ask", lambda *args, **kwargs: kwargs["default"])

    path = setup_wizard.run_setup_wizard(
        provider_override="anthropic",
        home=tmp_path / "home",
        console=None,
    )

    assert path.exists()
