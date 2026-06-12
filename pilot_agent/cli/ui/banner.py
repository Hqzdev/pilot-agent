"""Startup banner rendering for Pilot Agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from pilot_agent.agent.phases import PIPELINE
from pilot_agent.cli.ui.components import key_value_grid
from pilot_agent.cli.ui.theme import glyphs

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
    art = Text(ASCII_ART, style="pilot_agent.accent")
    console.print(art)
    phase_idx = PIPELINE.index(state.phase) + 1 if state.phase in PIPELINE else 0
    phase_total = len(PIPELINE)
    metadata = key_value_grid(
        [
            ("model", f"{state.provider}:{state.model}"),
            (
                "project",
                f"{state.project_root}          phase  {g.PHASE} {state.phase} "
                f"({phase_idx}/{phase_total})",
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
    header.add_row(Text("Pilot Agent " + state.version, style="pilot_agent.accent"))
    header.add_row("idea -> deployed MVP")
    console.print(header)
    console.print(metadata)
    console.print(
        Text(
            "/help - commands · /model - switch model · Ctrl+C - interrupt",
            style="pilot_agent.muted",
        )
    )
