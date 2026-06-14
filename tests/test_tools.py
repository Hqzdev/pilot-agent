from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from pilot_agent.agent.hooks import TOOL_REQUEST_MIDDLEWARE, RuntimeHooks
from pilot_agent.agent.tool_guardrails import ToolCallGuardrailController
from pilot_agent.agent.types import ToolCall
from pilot_agent.tools.ask_user import AskUserTool
from pilot_agent.tools.base import Tool, ToolRegistry, ToolSearchSettings
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


class DeferredEchoTool(EchoTool):
    name = "deferred_echo"
    description = "Echo text through a deferred tool."
    deferrable = True


class ParallelProbeTool(Tool):
    name = "parallel_probe"
    description = "Probe parallel execution."
    parallel_safe = True
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
        "additionalProperties": False,
    }
    active = 0
    max_active = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        with cls.lock:
            cls.active = 0
            cls.max_active = 0

    def execute(self, **kwargs: Any) -> str:
        with self.lock:
            self.__class__.active += 1
            self.__class__.max_active = max(self.__class__.max_active, self.__class__.active)
        time.sleep(0.05)
        with self.lock:
            self.__class__.active -= 1
        return str(kwargs["label"])


class PathScopedProbeTool(ParallelProbeTool):
    name = "path_probe"
    description = "Probe path scoped parallel execution."
    parallel_safe = False
    path_scope_args = ("path",)
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> str:
        return super().execute(label=str(kwargs["path"]))


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


def test_registry_redacts_secrets_in_content_and_artifact(tmp_path: Path) -> None:
    registry = ToolRegistry([EchoTool()], tmp_path)

    result = registry.execute(
        ToolCall("secret", "echo", {"text": "ANTHROPIC_API_KEY=sk-ant-secretvalue123456"})
    )

    assert "secretvalue" not in result.content
    assert result.artifact_path is not None
    assert "secretvalue" not in Path(result.artifact_path).read_text(encoding="utf-8")


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


def test_file_tools_deny_secret_env_files(tmp_path: Path) -> None:
    registry = ToolRegistry(
        [ReadFileTool(tmp_path), WriteFileTool(tmp_path)],
        tmp_path,
    )
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")

    read = registry.execute(ToolCall("read-env", "read_file", {"path": ".env"}))
    write = registry.execute(
        ToolCall("write-env", "write_file", {"path": ".env.local", "content": "TOKEN=x"})
    )

    assert read.is_error is True
    assert write.is_error is True
    assert "Access denied" in read.content
    assert "Access denied" in write.content


def test_read_file_allows_pilot_agent_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_read_file_denies_pilot_agent_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / "credentials.yaml").write_text("anthropic:\n  api_key: secret\n", encoding="utf-8")
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    registry = ToolRegistry([ReadFileTool(tmp_path / "project")], tmp_path / "project")

    result = registry.execute(
        ToolCall("creds", "read_file", {"path": str(home / "credentials.yaml")})
    )

    assert result.is_error is True
    assert "credential store" in result.content


def test_tool_guardrails_warn_on_repeated_failure(tmp_path: Path) -> None:
    guardrails = ToolCallGuardrailController()
    registry = ToolRegistry([EchoTool()], tmp_path, guardrails=guardrails)

    first = registry.execute(ToolCall("bad1", "echo", {}))
    second = registry.execute(ToolCall("bad2", "echo", {}))

    assert first.is_error is True
    assert second.is_error is True
    assert "Tool loop warning" in second.content


def test_runtime_hooks_can_mutate_block_and_transform_tool_calls(tmp_path: Path) -> None:
    hooks = RuntimeHooks()
    observed: list[tuple[str, str]] = []

    def normalize_args(args: dict[str, Any], **_: Any) -> dict[str, Any]:
        return {
            "name": "normalize_args",
            "args": {"text": str(args["text"]).upper()},
            "changed": True,
        }

    def pre_tool(args: dict[str, Any], **_: Any) -> dict[str, str] | None:
        if args["text"] == "BLOCK":
            return {"action": "block", "message": "blocked by test hook"}
        observed.append(("pre", str(args["text"])))
        return None

    hooks.register_middleware(TOOL_REQUEST_MIDDLEWARE, normalize_args)
    hooks.register_hook("pre_tool_call", pre_tool)
    hooks.register_hook(
        "post_tool_call",
        lambda result, **_: observed.append(("post", str(result))),
    )
    hooks.register_hook("transform_tool_result", lambda result, **_: f"{result}!")
    registry = ToolRegistry([EchoTool()], tmp_path, hooks=hooks)

    ok = registry.execute(ToolCall("ok", "echo", {"text": "hello"}))
    blocked = registry.execute(ToolCall("blocked", "echo", {"text": "block"}))

    assert ok.content == "HELLO!"
    assert blocked.is_error is True
    assert "blocked by test hook" in blocked.content
    assert observed == [("pre", "HELLO"), ("post", "HELLO"), ("post", "blocked by test hook")]


def test_tool_search_bridge_defers_and_scopes_tools(tmp_path: Path) -> None:
    registry = ToolRegistry(
        [EchoTool(), DeferredEchoTool()],
        tmp_path,
        tool_search=ToolSearchSettings(enabled="on", search_default_limit=2),
    )

    names = [spec.name for spec in registry.specs()]
    search = registry.execute(ToolCall("search", "tool_search", {"query": "deferred echo"}))
    describe = registry.execute(
        ToolCall("describe", "tool_describe", {"name": "deferred_echo"})
    )
    called = registry.execute(
        ToolCall(
            "call",
            "tool_call",
            {"name": "deferred_echo", "arguments": {"text": "hi"}},
        )
    )
    out_of_scope = registry.execute(
        ToolCall(
            "scope",
            "tool_call",
            {"name": "deferred_echo", "arguments": {"text": "hi"}},
        ),
        context={"allowed_tools": ["echo"]},
    )

    assert "echo" in names
    assert "deferred_echo" not in names
    assert {"tool_search", "tool_describe", "tool_call"}.issubset(names)
    assert json.loads(search.content)["matches"][0]["name"] == "deferred_echo"
    assert json.loads(describe.content)["name"] == "deferred_echo"
    assert called.content == "hi"
    assert out_of_scope.is_error is True
    assert "unavailable in this scope" in out_of_scope.content


def test_execute_batch_parallelizes_only_safe_groups(tmp_path: Path) -> None:
    ParallelProbeTool.reset()
    registry = ToolRegistry([ParallelProbeTool(), PathScopedProbeTool()], tmp_path)

    registry.execute_batch(
        [
            ToolCall("a", "parallel_probe", {"label": "a"}),
            ToolCall("b", "parallel_probe", {"label": "b"}),
        ]
    )
    assert ParallelProbeTool.max_active >= 2

    PathScopedProbeTool.reset()
    registry.execute_batch(
        [
            ToolCall("c", "path_probe", {"path": "a.txt"}),
            ToolCall("d", "path_probe", {"path": "b.txt"}),
        ]
    )
    assert PathScopedProbeTool.max_active >= 2

    PathScopedProbeTool.reset()
    registry.execute_batch(
        [
            ToolCall("e", "path_probe", {"path": "same.txt"}),
            ToolCall("f", "path_probe", {"path": "same.txt"}),
        ]
    )
    assert PathScopedProbeTool.max_active == 1


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
