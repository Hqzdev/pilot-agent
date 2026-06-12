from __future__ import annotations

import re
from pathlib import Path

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from devagent.agent.types import ToolCall, ToolResult
from devagent.cli.ui.banner import BannerState, render_banner
from devagent.cli.ui.components import create_console
from devagent.cli.ui.input import SlashCompleter
from devagent.cli.ui.renderer import Renderer
from devagent.cli.ui.status import StatusBar, StatusState


def test_tool_renderer_snapshot() -> None:
    console = create_console(color="never", record=True, width=100)
    renderer = Renderer(console)
    call = ToolCall(id="call-1", name="bash", arguments={"command": "npm run build"})
    result = ToolResult(
        tool_call_id="call-1",
        content="[exit 1]\nerror TS2304: Cannot find name 'foo'\nsrc/index.ts:12",
        is_error=True,
    )

    renderer.render_tool_result(call, result, elapsed_s=0.8)
    text = console.export_text()
    snapshot = Path("tests/snapshots/tool_error.txt").read_text(encoding="utf-8")

    assert text == snapshot


def test_banner_and_status_fit_80_columns(tmp_path: Path) -> None:
    console = create_console(color="never", record=True, width=80)

    render_banner(
        console,
        BannerState(
            version="0.1.0",
            provider="anthropic",
            model="claude-sonnet-4-6",
            project_root=tmp_path,
            phase="coding",
            lessons_count=12,
            skills_count=9,
            resumed=True,
            turns=47,
        ),
        force=True,
    )
    console.print(
        StatusBar(console).render(
            StatusState(
                phase="coding",
                phase_index=3,
                phase_total=5,
                todo_done=8,
                todo_total=19,
                context_percent=41,
                model="claude-sonnet-4-6",
                input_tokens=1000,
                output_tokens=2000,
            )
        )
    )

    assert all(len(line) <= 80 for line in console.export_text().splitlines())


def test_no_color_export_has_no_ansi_sequences() -> None:
    console = create_console(color="never", record=True, width=80)
    Renderer(console).render_agent("**hello**")

    assert "\x1b[" not in console.export_text()


def test_slash_completer_filters_commands_and_skills() -> None:
    completer = SlashCompleter(skill_names=["nextjs-vercel-deploy", "readme-structure"])

    commands = list(completer.get_completions(Document("/mo"), CompleteEvent()))
    skills = list(completer.get_completions(Document("/skills read"), CompleteEvent()))

    assert [item.text for item in commands] == ["/model"]
    assert [item.text for item in skills] == ["readme-structure"]


def test_ui_hex_colors_only_live_in_theme() -> None:
    ui_dir = Path("devagent/cli/ui")
    offenders: list[str] = []
    pattern = re.compile(r"#[0-9A-Fa-f]{6}")
    for path in ui_dir.glob("*.py"):
        if path.name == "theme.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))

    assert offenders == []
