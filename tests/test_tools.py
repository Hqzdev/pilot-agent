from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from pilot_agent.agent.types import ToolCall
from pilot_agent.tools.ask_user import AskUserTool
from pilot_agent.tools.base import Tool, ToolRegistry
from pilot_agent.tools.bash import BashTool
from pilot_agent.tools.file_ops import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from pilot_agent.tools.phase_tools import CompletePhaseTool
from pilot_agent.tools.run_check import RunAndCheckTool
from pilot_agent.tools.skill_tools import LoadSkillTool, SaveSkillTool


class EchoTool(Tool):
    name = "echo"
    description = "Echo text."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> str:
        text = str(kwargs["text"])
        return text


class SlowTool(EchoTool):
    name = "slow"
    timeout_s = 0

    def execute(self, **kwargs: Any) -> str:
        time.sleep(0.2)
        return "too late"


def test_registry_validates_writes_artifact_and_truncates(tmp_path: Path) -> None:
    registry = ToolRegistry([EchoTool()], tmp_path)
    long_text = "a" * 9_000

    result = registry.execute(ToolCall("call_1", "echo", {"text": long_text}))

    assert result.truncated is True
    assert result.artifact_path is not None
    assert Path(result.artifact_path).read_text() == long_text
    assert len(result.content) < len(long_text)
    assert "full output" in result.content


def test_registry_validation_errors_also_write_artifact(tmp_path: Path) -> None:
    registry = ToolRegistry([EchoTool()], tmp_path)

    result = registry.execute(ToolCall("bad", "echo", {}))

    assert result.is_error is True
    assert result.artifact_path is not None
    assert Path(result.artifact_path).exists()
    assert "validation failed" in result.content


def test_registry_timeout_writes_error_artifact(tmp_path: Path) -> None:
    registry = ToolRegistry([SlowTool()], tmp_path)

    result = registry.execute(ToolCall("slow_call", "slow", {"text": "x"}))

    assert result.is_error is True
    assert result.artifact_path is not None
    assert Path(result.artifact_path).read_text().startswith("tool timed out")


def test_bash_runs_in_project_root_and_blocks_dangerous_commands(tmp_path: Path) -> None:
    registry = ToolRegistry([BashTool(tmp_path)], tmp_path)

    ok = registry.execute(ToolCall("pwd", "bash", {"command": "pwd"}))
    blocked = registry.execute(ToolCall("blocked", "bash", {"command": "sudo whoami"}))

    assert ok.content.startswith("[exit 0]")
    assert str(tmp_path) in ok.content
    assert blocked.is_error is True
    assert "blocked dangerous command" in blocked.content


def test_file_tools_enforce_paths_and_edit_uniqueness(tmp_path: Path) -> None:
    registry = ToolRegistry(
        [
            ReadFileTool(tmp_path),
            WriteFileTool(tmp_path),
            EditFileTool(tmp_path),
            ListFilesTool(tmp_path),
        ],
        tmp_path,
    )
    write = registry.execute(
        ToolCall("write", "write_file", {"path": "a.txt", "content": "x\nx\n"})
    )
    duplicate = registry.execute(
        ToolCall("edit", "edit_file", {"path": "a.txt", "old_str": "x", "new_str": "y"})
    )
    read = registry.execute(
        ToolCall("read", "read_file", {"path": "a.txt", "offset": 1, "limit": 1})
    )
    outside = registry.execute(
        ToolCall("outside", "write_file", {"path": "../escape.txt", "content": "no"})
    )

    assert write.content == "written 4 bytes to a.txt"
    assert duplicate.is_error is True
    assert "found 2" in duplicate.content
    assert "   1\u2192x" in read.content
    assert outside.is_error is True


def test_read_file_allows_home_devagent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    memory = home
    memory.mkdir(parents=True)
    (memory / "lessons.md").write_text("lesson", encoding="utf-8")
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    registry = ToolRegistry([ReadFileTool(tmp_path / "project")], tmp_path / "project")

    result = registry.execute(
        ToolCall("home", "read_file", {"path": str(memory / "lessons.md")})
    )

    assert "lesson" in result.content


def test_run_and_check_kills_sleep_process(tmp_path: Path) -> None:
    registry = ToolRegistry([RunAndCheckTool(tmp_path)], tmp_path)

    result = registry.execute(
        ToolCall("run", "run_and_check", {"command": "sleep 999", "wait_s": 0})
    )
    payload = json.loads(result.content)
    ps = subprocess.run(["pgrep", "-f", "sleep 999"], text=True, capture_output=True, check=False)

    assert payload["started"] is True
    assert payload["verdict"] == "pass"
    assert "sleep 999" not in ps.stdout


def test_tool_schemas_exist(tmp_path: Path) -> None:
    class Backend:
        def load(self, name: str) -> str:
            return name

        def save(self, content: str) -> str:
            return content

    tools = [
        AskUserTool(),
        LoadSkillTool(Backend()),
        SaveSkillTool(Backend()),
        CompletePhaseTool(),
    ]

    for tool in tools:
        assert tool.spec().parameters["type"] == "object"
