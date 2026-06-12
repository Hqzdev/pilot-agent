"""Reusable Rich components for Pilot Agent CLI screens."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from rich import box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table

from pilot_agent.cli.ui.theme import RICH_THEME, color_enabled


def create_console(
    *,
    color: str = "auto",
    record: bool = False,
    width: int | None = None,
) -> Console:
    return Console(
        theme=RICH_THEME,
        no_color=not color_enabled(color),
        record=record,
        width=width,
    )


def panel(
    renderable: RenderableType,
    *,
    title: str | None = None,
    border_style: str = "pilot_agent.accent.dim",
) -> Panel:
    return Panel(renderable, title=title, border_style=border_style)


def simple_table(*columns: str) -> Table:
    table = Table(*columns, box=box.SIMPLE_HEAD, header_style="pilot_agent.muted")
    return table


def key_value_grid(rows: Iterable[tuple[str, Any]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="pilot_agent.muted")
    table.add_column()
    for key, value in rows:
        table.add_row(key, str(value))
    return table


def plain_mode() -> bool:
    return bool(os.environ.get("NO_COLOR")) or not os.isatty(1)
