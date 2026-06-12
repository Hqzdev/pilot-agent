"""Shared console theme for DevAgent rich and prompt_toolkit UI."""

from __future__ import annotations

import os
import sys

from rich.style import Style
from rich.theme import Theme


class Palette:
    ACCENT = "#00D4AA"
    ACCENT_DIM = "#0E8C75"
    OK = "#22C55E"
    WARN = "#F59E0B"
    ERR = "#EF4444"
    INFO = "#60A5FA"
    MUTED = "#71717A"
    USER = "#E4E4E7"
    AGENT = "default"


class Glyphs:
    OK = "✓"
    ERR = "✗"
    WARN = "⚠"
    TOOL = "⚙"
    PHASE = "◆"
    ARROW = "→"
    SPINNER = "dots"
    PROMPT = "❯"
    BULLET = "·"
    TODO_DONE = "▰"
    TODO_OPEN = "▱"


class AsciiGlyphs:
    OK = "+"
    ERR = "x"
    WARN = "!"
    TOOL = "*"
    PHASE = "*"
    ARROW = ">"
    SPINNER = "dots"
    PROMPT = ">"
    BULLET = "-"
    TODO_DONE = "#"
    TODO_OPEN = "-"


def color_enabled(config_value: str = "auto") -> bool:
    if os.environ.get("NO_COLOR") or config_value == "never":
        return False
    if config_value == "always":
        return True
    return sys.stdout.isatty()


def unicode_enabled() -> bool:
    encoding = (sys.stdout.encoding or "").lower()
    return "utf" in encoding


def glyphs() -> type[Glyphs] | type[AsciiGlyphs]:
    return Glyphs if unicode_enabled() else AsciiGlyphs


RICH_THEME = Theme(
    {
        "devagent.accent": Style(color=Palette.ACCENT),
        "devagent.accent.dim": Style(color=Palette.ACCENT_DIM),
        "devagent.ok": Style(color=Palette.OK),
        "devagent.warn": Style(color=Palette.WARN),
        "devagent.err": Style(color=Palette.ERR),
        "devagent.info": Style(color=Palette.INFO),
        "devagent.muted": Style(color=Palette.MUTED),
        "devagent.user": Style(color=Palette.USER),
        "devagent.agent": Style(color=Palette.AGENT),
    }
)
