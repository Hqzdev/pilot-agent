from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from pilot_agent.cli import app, setup_wizard
from pilot_agent.cli.auth import ValidationResult
from pilot_agent.config.credentials import get_credential, set_credential
from pilot_agent.config.schema import load_config


def test_setup_with_existing_env_key_writes_config_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    monkeypatch.setattr(setup_wizard, "_docker_available", lambda: True)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["setup", "--provider", "anthropic"],
        input="\nn\n",
    )

    assert result.exit_code == 0
    cfg_path = tmp_path / "home" / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    assert "test-secret" not in text
    data = yaml.safe_load(text)
    assert data["provider"] == "anthropic"
    assert data["api_key_env"] == "ANTHROPIC_API_KEY"
    assert data["phases"]["deploy"]["enabled"] is False


def test_setup_credentials_secret_has_0600_permissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(setup_wizard, "_docker_available", lambda: True)
    monkeypatch.setattr(
        setup_wizard,
        "validate_provider_key",
        lambda *args, **kwargs: ValidationResult("pass", "ok", 1),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["setup", "--provider", "anthropic"],
        input="secret-key\n\nn\n",
    )

    credentials_path = tmp_path / "home" / "credentials.yaml"
    assert result.exit_code == 0
    assert "secret-key" not in (tmp_path / "home" / "config.yaml").read_text(encoding="utf-8")
    credentials = yaml.safe_load(credentials_path.read_text(encoding="utf-8"))
    assert credentials["anthropic"]["api_key"] == "secret-key"
    assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600


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


def test_credentials_env_overrides_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    set_credential("anthropic", "from-storage", home)
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")

    cfg = load_config(home=home, project_root=tmp_path / "project")

    assert get_credential("anthropic", home) == "from-env"
    assert cfg.resolve_key() == "from-env"


def test_auth_status_masks_and_remove_deletes_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    runner = CliRunner()

    set_result = runner.invoke(app, ["auth", "set", "brave", "brave-secret-1234"])
    status_result = runner.invoke(app, ["auth", "status"])
    remove_result = runner.invoke(app, ["auth", "remove", "brave"])

    assert set_result.exit_code == 0
    assert status_result.exit_code == 0
    assert "brave-" in status_result.output
    assert "1234" in status_result.output
    assert "brave-secret-1234" not in status_result.output
    assert remove_result.exit_code == 0
    assert get_credential("brave", home) is None


def test_delete_all_removes_pilot_agent_files_without_docker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    source = tmp_path / "source"
    bin_dir = tmp_path / "bin"
    project = tmp_path / "project"
    home.mkdir()
    source.mkdir()
    bin_dir.mkdir()
    project.mkdir()
    (home / "config.yaml").write_text("provider: anthropic\n", encoding="utf-8")
    (home / "credentials.yaml").write_text("anthropic:\n  api_key: secret\n", encoding="utf-8")
    (bin_dir / "pilot-agent").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (project / ".pilot-agent").mkdir()
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    monkeypatch.setenv("PILOT_AGENT_SRC", str(source))
    monkeypatch.setenv("PILOT_AGENT_BIN_DIR", str(bin_dir))
    monkeypatch.chdir(project)
    runner = CliRunner()

    result = runner.invoke(app, ["delete", "--all", "--yes"])

    assert result.exit_code == 0
    assert "Docker images and volumes are not removed" in result.output
    assert not home.exists()
    assert not source.exists()
    assert not (bin_dir / "pilot-agent").exists()
    assert not (project / ".pilot-agent").exists()


def test_model_direct_switch_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
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
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    result = runner.invoke(app, ["model", "bad:model"])

    assert result.exit_code == 1
    assert "Run: pilot-agent setup" in result.output


def test_setup_wizard_can_be_called_directly_with_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setattr(
        setup_wizard.PilotAgentInput,
        "prompt",
        lambda self, *args, **kwargs: kwargs["default"],
    )
    monkeypatch.setattr(
        setup_wizard.PilotAgentInput,
        "confirm",
        lambda self, *args, **kwargs: kwargs["default"],
    )
    monkeypatch.setattr(
        setup_wizard.PilotAgentInput,
        "ask_int",
        lambda self, *args, **kwargs: kwargs["default"],
    )
    monkeypatch.setattr(
        setup_wizard.PilotAgentInput,
        "select",
        lambda self, message, choices, **kwargs: choices[kwargs["default"]][0],
    )
    monkeypatch.setattr(setup_wizard, "_docker_available", lambda: True)

    path = setup_wizard.run_setup_wizard(
        provider_override="anthropic",
        home=tmp_path / "home",
        console=None,
    )

    assert path.exists()
