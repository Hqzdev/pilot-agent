from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from devagent.agent.context import ContextManager, StaticSummaryProvider
from devagent.agent.loop import AgentLoop, restore_phase_from_session
from devagent.agent.phases import PHASES, PIPELINE
from devagent.agent.prompts import COMMON_PREFIX
from devagent.agent.state import init_project_state, read_session_messages, write_session_record
from devagent.agent.types import CompletionResponse, Message, Role, ToolCall, ToolSpec
from devagent.cli import app
from devagent.providers.base import Provider
from devagent.tools.base import Tool, ToolRegistry
from devagent.tools.skill_tools import LoadSkillTool


class CompleteOnlyProvider(Provider):
    def __init__(self) -> None:
        super().__init__("test", "key")
        self.system_seen = ""

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        self.system_seen = system
        return CompletionResponse(
            message=Message(
                role=Role.ASSISTANT,
                content="done",
                tool_calls=[ToolCall("phase", "complete_phase", {"summary": "brief"})],
            ),
            stop_reason="tool_use",
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    def count_tokens(self, system: str, messages: list[Message]) -> int:
        return len(system)

    @property
    def context_window(self) -> int:
        return 100_000


class NoopTool(Tool):
    name = "noop"
    description = "noop"
    parameters: dict[str, Any] = {"type": "object", "additionalProperties": False}

    def execute(self, **kwargs: Any) -> str:
        return "noop"


class SequenceProvider(CompleteOnlyProvider):
    def __init__(self, calls: list[ToolCall]):
        super().__init__()
        self.calls = calls

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        self.system_seen = system
        return CompletionResponse(
            message=Message(role=Role.ASSISTANT, tool_calls=[self.calls.pop(0)]),
            stop_reason="tool_use",
            usage={"input_tokens": 1, "output_tokens": 1},
        )


class SkillBackend:
    def __init__(self) -> None:
        self.outcomes: list[tuple[str, bool]] = []

    def load(self, name: str) -> str:
        return f"skill {name}"

    def save(self, content: str) -> str:
        return content

    def index_for_prompt(self, phase: str, stack: list[str]) -> str:
        return "- nextjs-vercel-deploy: deploy"

    def record_outcome(self, name: str, success: bool) -> None:
        self.outcomes.append((name, success))


def test_phase_pipeline_and_tools_exact() -> None:
    assert PIPELINE == ["discovery", "planning", "coding", "deploy", "marketing"]
    assert PHASES["discovery"].tools == ["ask_user", "complete_phase"]
    assert PHASES["deploy"].tools == [
        "bash",
        "run_and_check",
        "read_file",
        "edit_file",
        "load_skill",
        "save_skill",
        "ask_user",
        "complete_phase",
    ]


def test_prompts_include_required_common_rules() -> None:
    assert "Update .devagent/STATE.md" in COMMON_PREFIX
    assert "Call load_skill(name)" in COMMON_PREFIX
    assert "read_file existing files" in COMMON_PREFIX


def test_loop_turn_complete_phase_logs_and_advances(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Demo")
    provider = CompleteOnlyProvider()
    registry = ToolRegistry([NoopTool()], tmp_path)
    loop = AgentLoop(
        project_root=tmp_path,
        provider=provider,
        registry=registry,
        ctx=ContextManager(
            StaticSummaryProvider(),
            session_log=tmp_path / ".devagent/session.jsonl",
        ),
    )

    loop.run_turn()

    assert "# STATE.md" in provider.system_seen
    assert loop.phase is not None
    assert loop.phase.name == "planning"
    assert len(read_session_messages(tmp_path)) == 2
    assert "brief" in (tmp_path / ".devagent" / "STATE.md").read_text()
    assert "phase_change" in (tmp_path / ".devagent" / "session.jsonl").read_text()


def test_loop_pins_loaded_skill_and_records_outcome(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Demo")
    backend = SkillBackend()
    provider = SequenceProvider(
        [
            ToolCall("load", "load_skill", {"name": "nextjs-vercel-deploy"}),
            ToolCall("phase", "complete_phase", {"summary": "deploy done"}),
            ToolCall("phase-2", "complete_phase", {"summary": "synthesis done"}),
        ]
    )
    loop = AgentLoop(
        project_root=tmp_path,
        provider=provider,
        registry=ToolRegistry([LoadSkillTool(backend)], tmp_path),
        ctx=ContextManager(
            StaticSummaryProvider(),
            session_log=tmp_path / ".devagent/session.jsonl",
        ),
        skills=backend,
        phase_name="deploy",
    )

    loop.run_turn()
    assert loop.history[-1].pinned is True
    loop.run_turn()
    assert loop.phase is not None
    assert loop.phase.name == "deploy"
    assert any("Фаза deploy завершена" in message.content for message in loop.history)
    assert backend.outcomes == []
    loop.run_turn()

    assert backend.outcomes == [("nextjs-vercel-deploy", True)]
    assert all(not message.pinned for message in loop.history if message.phase == "deploy")
    assert loop.phase is not None
    assert loop.phase.name == "marketing"


def test_session_restore_phase(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Demo")
    write_session_record(tmp_path, {"_type": "phase_change", "from": "discovery", "to": "planning"})

    assert restore_phase_from_session(tmp_path) == "planning"


def test_slash_skip_advances_phase(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Demo")
    loop = AgentLoop(
        project_root=tmp_path,
        provider=CompleteOnlyProvider(),
        registry=ToolRegistry([NoopTool()], tmp_path),
        ctx=ContextManager(
            StaticSummaryProvider(),
            session_log=tmp_path / ".devagent/session.jsonl",
        ),
    )

    loop.handle_slash_command("/skip")

    assert loop.phase is not None
    assert loop.phase.name == "planning"
    assert "phase_change" in (tmp_path / ".devagent" / "session.jsonl").read_text()


def test_slash_model_switches_provider(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Demo")
    new_provider = StaticSummaryProvider(context_window=500)
    seen: list[str] = []
    loop = AgentLoop(
        project_root=tmp_path,
        provider=CompleteOnlyProvider(),
        registry=ToolRegistry([NoopTool()], tmp_path),
        ctx=ContextManager(StaticSummaryProvider(context_window=1000), session_log=None),
        model_switcher=lambda target: seen.append(target) or new_provider,
    )

    loop.handle_slash_command("/model openrouter:qwen/qwen3-coder")

    assert seen == ["openrouter:qwen/qwen3-coder"]
    assert loop.provider is new_provider
    assert loop.ctx.threshold == 350


def test_slash_undo_removes_last_assistant_tool_pair(tmp_path: Path) -> None:
    init_project_state(tmp_path, "Demo")
    loop = AgentLoop(
        project_root=tmp_path,
        provider=CompleteOnlyProvider(),
        registry=ToolRegistry([NoopTool()], tmp_path),
        ctx=ContextManager(StaticSummaryProvider(), session_log=None),
        history=[
            Message(role=Role.USER, content="keep"),
            Message(role=Role.ASSISTANT, content="remove"),
            Message(role=Role.TOOL),
        ],
    )

    loop.handle_slash_command("/undo")

    assert [message.role for message in loop.history] == [Role.USER]
    assert loop.history[0].content == "keep"


def test_cli_help_init_config_and_skills(tmp_path: Path) -> None:
    runner = CliRunner()

    help_result = runner.invoke(app, ["--help"])
    init_result = runner.invoke(app, ["init", str(tmp_path / "proj")])
    config_result = runner.invoke(app, ["config"])
    skills_result = runner.invoke(app, ["skills", "list"])

    assert help_result.exit_code == 0
    assert "run" in help_result.output
    assert init_result.exit_code == 0
    assert (tmp_path / "proj" / ".devagent" / "STATE.md").exists()
    assert config_result.exit_code == 0
    assert "api_key_present" in config_result.output
    assert skills_result.exit_code == 0
    assert "nextjs-vercel-deploy" in skills_result.output


def test_cli_run_missing_api_key_is_clear(monkeypatch: Any) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert "Missing API key. Set ANTHROPIC_API_KEY" in result.output
    assert "Traceback" not in result.output
