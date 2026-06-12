from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pilot_agent.cli import app


def test_doctor_json_reports_actionable_missing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 1
    checks = json.loads(result.output)
    key_check = next(item for item in checks if item["name"] == "provider API key")
    assert key_check["status"] == "fail"
    assert "pilot-agent auth set anthropic" in key_check["fix"]


def test_doctor_json_reports_broken_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("ui:\n  color: sometimes\n", encoding="utf-8")
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    runner = CliRunner()

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 1
    checks = json.loads(result.output)
    config_check = next(item for item in checks if item["name"] == "config.yaml valid")
    assert config_check["status"] == "fail"
    assert "setup --reconfigure" in config_check["fix"]


def test_status_reads_phase_todo_and_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    agent_dir = project / ".pilot-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "STATE.md").write_text(
        "# Project\n## TODO\n- [x] done\n- [ ] next\n## Done\n",
        encoding="utf-8",
    )
    (agent_dir / "session.jsonl").write_text(
        '{"_type":"phase_change","from":"planning","to":"coding"}\n'
        '{"_type":"Message","role":"assistant","content":"ok","tokens":13}\n',
        encoding="utf-8",
    )
    runner = CliRunner()

    monkeypatch.chdir(project)
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "coding" in result.output
    assert "1/2" in result.output
    assert "13" in result.output


def test_sessions_list_shows_current_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    agent_dir = project / ".pilot-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "session.jsonl").write_text(
        '{"_type":"phase_change","from":"discovery","to":"planning"}\n',
        encoding="utf-8",
    )
    runner = CliRunner()

    monkeypatch.chdir(project)
    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0
    assert "planning" in result.output
    assert "project" in result.output


def test_lessons_clear_and_skills_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "lessons.md").write_text("lesson", encoding="utf-8")
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    runner = CliRunner()

    show_skill = runner.invoke(app, ["skills", "show", "readme-structure"])
    clear = runner.invoke(app, ["lessons", "clear", "--yes"])
    lessons = runner.invoke(app, ["lessons"])

    assert show_skill.exit_code == 0
    assert "README" in show_skill.output
    assert clear.exit_code == 0
    assert lessons.exit_code == 0
    assert lessons.output.strip() == ""
