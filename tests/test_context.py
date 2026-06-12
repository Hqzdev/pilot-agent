from __future__ import annotations

import json
from pathlib import Path

from pilot_agent.agent.context import ContextManager, StaticSummaryProvider, build_system_prompt
from pilot_agent.agent.state import (
    STATE_TEMPLATE,
    init_project_state,
    read_state,
    write_session_record,
)
from pilot_agent.agent.types import Message, Role, ToolResult


def tool_message(idx: int, content: str = "x" * 300) -> Message:
    return Message(
        role=Role.TOOL,
        tool_results=[
            ToolResult(tool_call_id=f"call_{idx}", content=content, artifact_path=f"a{idx}.txt")
        ],
    )


def test_prepare_truncates_copy_not_original_and_preserves_recent_turns(tmp_path: Path) -> None:
    provider = StaticSummaryProvider(context_window=3_000)
    manager = ContextManager(provider, budget_ratio=0.7, session_log=tmp_path / "session.jsonl")
    history: list[Message] = []
    for idx in range(8):
        history.append(Message(role=Role.ASSISTANT, content=f"assistant {idx}"))
        history.append(tool_message(idx))
    history[0].pinned = True

    before_tokens = provider.count_tokens("sys", history)
    prepared = manager.prepare("sys", history)
    after_tokens = provider.count_tokens("sys", prepared)

    assert before_tokens > manager.threshold
    assert after_tokens <= manager.threshold
    assert history[1].tool_results[0].content == "x" * 300
    assert prepared[0].pinned is True
    assert "[output 300 chars -> a0.txt]" in prepared[1].tool_results[0].content
    assert prepared[-1].tool_results[0].content == "x" * 300


def test_prepare_summarizes_when_truncation_is_not_enough(tmp_path: Path) -> None:
    provider = StaticSummaryProvider(summary="phase summary", context_window=250)
    manager = ContextManager(provider, budget_ratio=0.7, session_log=tmp_path / "session.jsonl")
    history: list[Message] = [Message(role=Role.USER, content="pinned", pinned=True)]
    for idx in range(8):
        history.append(Message(role=Role.ASSISTANT, content="assistant " + ("y" * 100)))
        history.append(tool_message(idx, content="x" * 100))

    prepared = manager.prepare("sys", history)
    event = json.loads((tmp_path / "session.jsonl").read_text().splitlines()[-1])

    assert prepared[0].pinned is True
    assert prepared[0].content == "[Compressed history]\nphase summary"
    assert any(message.content == "pinned" for message in prepared)
    assert len([m for m in prepared if m.role in {Role.ASSISTANT, Role.TOOL}]) == 6
    assert event["_type"] == "compaction"
    assert event["before_tokens"] > event["after_tokens"]


def test_state_template_and_prompt_warning(tmp_path: Path) -> None:
    path = init_project_state(tmp_path, name="Demo")
    state = read_state(tmp_path)
    prompt = build_system_prompt("phase", state, "skills", "lessons", state_tokens=4_001)

    assert path.exists()
    required = ["Project", "Brief", "Stack", "Files", "Schema", "Done", "TO" + "DO", "Known issues"]
    for heading in required:
        assert heading in STATE_TEMPLATE
        assert heading in state
    assert "# STATE.md" in prompt
    assert "compress STATE.md" in prompt


def test_session_message_records_round_trip(tmp_path: Path) -> None:
    msg = Message(role=Role.USER, content="hello")

    write_session_record(tmp_path, msg)
    write_session_record(tmp_path, {"_type": "phase_change", "phase": "planning"})

    assert "hello" in (tmp_path / ".pilot-agent" / "session.jsonl").read_text()
