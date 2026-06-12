from __future__ import annotations

import json
from pathlib import Path

from pilot_agent.agent.memory import DEPLOY_SYNTHESIS_PROMPT, Memory
from pilot_agent.agent.state import read_session_messages, write_session_record
from pilot_agent.agent.types import Message, Role, ToolCall, ToolResult


def run_result(call_id: str, verdict: str, stderr_tail: str = "") -> ToolResult:
    return ToolResult(
        tool_call_id=call_id,
        content=json.dumps({"verdict": verdict, "stderr_tail": stderr_tail}),
    )


def test_fail_pass_cycle_generates_strict_lesson(tmp_path: Path) -> None:
    prompts: list[str] = []

    def summarize(prompt: str) -> str:
        prompts.append(prompt)
        return (
            "PROBLEM: uvicorn crashed because PORT was not wired\n"
            "FIX: Pass --port 8000 to uvicorn and probe the same port\n"
            "TAGS: fastapi, uvicorn"
        )

    memory = Memory(home=tmp_path, summarizer=summarize)
    fail = ToolCall("fail", "run_and_check", {"command": "uv run uvicorn main:app --port 8000"})
    fix = ToolCall("fix", "write_file", {"path": "main.py", "content": "fixed"})
    passed = ToolCall("pass", "run_and_check", {"command": "uv run uvicorn app:app --port 8000"})

    memory.observe(fail, run_result("fail", "fail", "Address already in use"))
    memory.observe(fix, ToolResult(tool_call_id="fix", content="written 5 bytes to main.py"))
    memory.observe(passed, run_result("pass", "pass"))

    lesson = (tmp_path / "lessons.md").read_text(encoding="utf-8")
    assert "PROBLEM: uvicorn crashed" in lesson
    assert "FIX: Pass --port 8000" in lesson
    assert "tags: fastapi, uvicorn" in lesson
    assert "Address already in use" in prompts[0]
    assert "write_file" in prompts[0]


def test_skip_lesson_is_not_written(tmp_path: Path) -> None:
    memory = Memory(home=tmp_path, summarizer=lambda prompt: "SKIP")
    fail = ToolCall("fail", "run_and_check", {"command": "npm run dev -- --port 3000"})
    passed = ToolCall("pass", "run_and_check", {"command": "npm run dev -- --port 3000"})

    memory.observe(fail, run_result("fail", "fail", "typo"))
    memory.observe(passed, run_result("pass", "pass"))

    assert not (tmp_path / "lessons.md").exists()


def test_relevant_lessons_filters_by_tags_newest_first(tmp_path: Path) -> None:
    (tmp_path / "lessons.md").write_text(
        """## [2026-06-10] tags: fastapi, uvicorn
PROBLEM: old
FIX: old fix

## [2026-06-11] tags: nextjs, vercel
PROBLEM: deploy
FIX: vercel fix

## [2026-06-12] tags: fastapi, sqlite
PROBLEM: schema
FIX: sqlite fix
""",
        encoding="utf-8",
    )

    lessons = Memory(home=tmp_path).relevant_lessons(["fastapi"], limit=2)

    assert lessons.index("PROBLEM: schema") < lessons.index("PROBLEM: old")
    assert "PROBLEM: deploy" not in lessons


def test_deploy_end_of_phase_injects_synthesis_prompt_once() -> None:
    history: list[Message] = []
    memory = Memory()

    memory.end_of_phase("deploy", history)
    memory.end_of_phase("deploy", history)

    assert len(history) == 1
    assert history[0].role is Role.USER
    assert history[0].content == DEPLOY_SYNTHESIS_PROMPT
    assert history[0].pinned is True


class Recorder:
    def __init__(self) -> None:
        self.outcomes: list[tuple[str, bool]] = []

    def record_outcome(self, name: str, success: bool) -> None:
        self.outcomes.append((name, success))


def test_end_of_session_marks_unfinished_loaded_skill_failed(tmp_path: Path) -> None:
    recorder = Recorder()
    load = Message(
        role=Role.ASSISTANT,
        phase="coding",
        tool_calls=[ToolCall("load", "load_skill", {"name": "python-deps-uv"})],
    )
    write_session_record(tmp_path, load)
    history = read_session_messages(tmp_path)
    memory = Memory(home=tmp_path / "home", skill_recorder=recorder)

    memory.end_of_session(history)
    memory.end_of_session(history)

    assert recorder.outcomes == [("python-deps-uv", False)]


def test_end_of_session_ignores_completed_phase_skills(tmp_path: Path) -> None:
    recorder = Recorder()
    history = [
        Message(
            role=Role.ASSISTANT,
            phase="coding",
            tool_calls=[ToolCall("load", "load_skill", {"name": "python-deps-uv"})],
        ),
        Message(
            role=Role.ASSISTANT,
            phase="coding",
            tool_calls=[ToolCall("done", "complete_phase", {"summary": "done"})],
        ),
    ]

    Memory(home=tmp_path, skill_recorder=recorder).end_of_session(history)

    assert recorder.outcomes == []
