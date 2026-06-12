from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devagent.cli import app
from devagent.config.schema import config_value, load_config, user_config_path


def test_full_config_defaults_include_onboarding_sections(tmp_path: Path) -> None:
    cfg = load_config(home=tmp_path / "home", project_root=tmp_path / "project")

    assert cfg.provider == "anthropic"
    assert cfg.phases.deploy.enabled is True
    assert cfg.phases.deploy.vercel_token_env == "VERCEL_TOKEN"
    assert cfg.phases.marketing.enabled is True
    assert cfg.ui.color == "auto"
    assert cfg.ui.show_token_counter is True


def test_config_precedence_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    (project / ".devagent").mkdir(parents=True)
    (home / "config.yaml").write_text(
        "provider: openai\nmodel: gpt-5\nbudget_ratio: 0.8\n",
        encoding="utf-8",
    )
    (project / ".devagent" / "config.yaml").write_text(
        "model: project-model\nphases:\n  deploy:\n    enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVAGENT_MODEL", "env-model")

    cfg = load_config(provider="anthropic", home=home, project_root=project)

    assert cfg.provider == "anthropic"
    assert cfg.model == "env-model"
    assert cfg.budget_ratio == 0.8
    assert cfg.phases.deploy.enabled is False
    assert cfg.sources["provider"] == "cli"
    assert cfg.sources["model"] == "env"
    assert cfg.sources["budget_ratio"] == "user"
    assert cfg.sources["phases.deploy.enabled"] == "project"
    assert cfg.sources["max_turns"] == "defaults"


def test_config_cli_table_get_set_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("DEVAGENT_HOME", str(home))
    runner = CliRunner()

    set_result = runner.invoke(app, ["config", "set", "phases.deploy.enabled", "false"])
    get_result = runner.invoke(app, ["config", "get", "phases.deploy.enabled"])
    path_result = runner.invoke(app, ["config", "path"])
    show_result = runner.invoke(app, ["config"])

    assert set_result.exit_code == 0
    assert get_result.exit_code == 0
    assert get_result.output.strip() == "False"
    assert path_result.output.strip() == str(user_config_path(home))
    assert show_result.exit_code == 0
    assert "phases.deploy.enabled" in show_result.output
    assert "user" in show_result.output


def test_global_config_flag_controls_reads_and_writes(tmp_path: Path) -> None:
    cfg_path = tmp_path / "custom.yaml"
    runner = CliRunner()

    set_result = runner.invoke(
        app,
        ["--config", str(cfg_path), "config", "set", "provider", "openai"],
    )
    get_result = runner.invoke(
        app,
        ["--config", str(cfg_path), "config", "get", "provider"],
    )

    assert set_result.exit_code == 0
    assert get_result.exit_code == 0
    assert get_result.output.strip() == "openai"


def test_config_set_rejects_invalid_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVAGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    result = runner.invoke(app, ["config", "set", "ui.color", "sometimes"])

    assert result.exit_code == 1
    assert "invalid value for ui.color" in result.output


def test_config_value_reads_nested_keys(tmp_path: Path) -> None:
    cfg = load_config(home=tmp_path / "home", project_root=tmp_path / "project")

    assert config_value(cfg, "phases.deploy.vercel_token_env") == "VERCEL_TOKEN"
