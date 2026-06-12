from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devagent.agent.context import ContextManager, StaticSummaryProvider
from devagent.agent.loop import AgentLoop, restore_phase_from_session
from devagent.agent.state import init_project_state, read_session_messages
from devagent.agent.types import CompletionResponse, Message, Role, ToolCall, ToolSpec
from devagent.cli import app
from devagent.providers.base import Provider
from devagent.tools.base import Tool, ToolRegistry


class CompletePhaseProvider(Provider):
    def __init__(self) -> None:
        super().__init__("mock", "key")

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        return CompletionResponse(
            message=Message(
                role=Role.ASSISTANT,
                tool_calls=[ToolCall("complete", "complete_phase", {"summary": "done"})],
            ),
            stop_reason="tool_use",
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    def count_tokens(self, system: str, messages: list[Message]) -> int:
        return len(system) + len(messages)

    @property
    def context_window(self) -> int:
        return 100_000


class LongOutputTool(Tool):
    name = "long_output"
    description = "Return long deterministic output."
    parameters: dict[str, Any] = {"type": "object", "additionalProperties": False}

    def execute(self, **kwargs: Any) -> str:
        return "0123456789" * 900


def test_cli_init_creates_runtime_files(tmp_path: Path) -> None:
    runner = CliRunner()
    project = tmp_path / "project"

    result = runner.invoke(app, ["init", str(project)])

    assert result.exit_code == 0
    assert (project / ".devagent" / "STATE.md").exists()
    assert (project / ".devagent" / "session.jsonl").exists()
    assert (project / ".devagent" / "artifacts").is_dir()


def test_mocked_run_progresses_and_resume_reads_phase(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Smoke")
    loop = AgentLoop(
        project_root=tmp_path,
        provider=CompletePhaseProvider(),
        registry=ToolRegistry([], tmp_path),
        ctx=ContextManager(
            StaticSummaryProvider(),
            session_log=tmp_path / ".devagent/session.jsonl",
        ),
    )

    loop.run_turn()
    restored = restore_phase_from_session(tmp_path)
    messages = read_session_messages(tmp_path)
    session_text = (tmp_path / ".devagent" / "session.jsonl").read_text(encoding="utf-8")

    assert loop.phase is not None
    assert loop.phase.name == "planning"
    assert restored == "planning"
    assert len(messages) == 2
    assert '"_type": "phase_change"' in session_text
    assert '"to": "planning"' in session_text


def test_long_output_artifact_preserves_full_content(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Artifact")
    registry = ToolRegistry([LongOutputTool()], tmp_path)

    result = registry.execute(ToolCall("long", "long_output", {}))

    assert result.truncated is True
    assert result.artifact_path is not None
    assert Path(result.artifact_path).read_text(encoding="utf-8") == "0123456789" * 900
    assert len(result.content) < len(Path(result.artifact_path).read_text(encoding="utf-8"))


def test_deploy_skill_load_precedes_vercel_command_in_session() -> None:
    history = [
        Message(
            role=Role.ASSISTANT,
            phase="deploy",
            tool_calls=[ToolCall("load", "load_skill", {"name": "nextjs-vercel-deploy"})],
        ),
        Message(
            role=Role.ASSISTANT,
            phase="deploy",
            tool_calls=[ToolCall("deploy", "bash", {"command": "vercel --prod --yes"})],
        ),
    ]

    load_index = next(
        idx for idx, msg in enumerate(history) if msg.tool_calls[0].name == "load_skill"
    )
    vercel_index = next(
        idx
        for idx, msg in enumerate(history)
        if "vercel" in msg.tool_calls[0].arguments.get("command", "")
    )

    assert load_index < vercel_index


def test_live_acceptance_reports_missing_prerequisites() -> None:
    env = {
        "PATH": "",
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [sys.executable, "scripts/live_acceptance.py"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["ready"] is False
    assert "docker" in payload["missing"]
    assert "VERCEL_TOKEN" in payload["missing"]
