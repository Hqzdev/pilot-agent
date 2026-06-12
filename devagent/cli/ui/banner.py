"""Startup banner rendering for DevAgent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from devagent.agent.phases import PIPELINE
from devagent.cli.ui.components import key_value_grid
from devagent.cli.ui.theme import glyphs

ASCII_ART = r"""
  ██████╗ ███████╗██╗   ██╗
  ██╔══██╗██╔════╝██║   ██║
  ██║  ██║█████╗  ██║   ██║
  ██████╔╝███████╗ ╚████╔╝
  ╚═════╝ ╚══════╝  ╚═══╝
""".strip("\n")


@dataclass(frozen=True)
class BannerState:
    version: str
    provider: str
    model: str
    project_root: Path
    phase: str
    lessons_count: int = 0
    skills_count: int = 0
    resumed: bool = False
    turns: int = 0


_shown = False


def render_banner(console: Console, state: BannerState, *, force: bool = False) -> None:
    global _shown
    if _shown and not force:
        return
    _shown = True
    g = glyphs()
    art = Text(ASCII_ART, style="devagent.accent")
    console.print(art)
    phase_idx = PIPELINE.index(state.phase) + 1 if state.phase in PIPELINE else 0
    metadata = key_value_grid(
        [
            ("model", f"{state.provider}:{state.model}"),
            (
                "project",
                f"{state.project_root}          phase  {g.PHASE} {state.phase} ({phase_idx}/5)",
            ),
            (
                "memory",
                f"{state.lessons_count} lessons {g.BULLET} {state.skills_count} skills  "
                f"{'session resumed' if state.resumed else 'new session'} {g.BULLET} "
                f"{state.turns} turns",
            ),
        ]
    )
    header = Table.grid(padding=(0, 3))
    header.add_row(Text("DevAgent " + state.version, style="devagent.accent"))
    header.add_row("idea -> deployed MVP")
    console.print(header)
    console.print(metadata)
    console.print(
        Text(
            "/help — команды · /model — сменить модель · Ctrl+C — прервать",
            style="devagent.muted",
        )
    )
