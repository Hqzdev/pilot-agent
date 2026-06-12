"""Status-bar helpers for phase, TODO, context, cost, and model summaries."""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.text import Text

from devagent.cli.ui.theme import glyphs

MODEL_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-1": (15.0, 75.0),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "qwen/qwen3-coder": (0.3, 1.2),
}


@dataclass(frozen=True)
class StatusState:
    phase: str
    phase_index: int
    phase_total: int
    todo_done: int
    todo_total: int
    context_percent: int
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class StatusBar:
    def __init__(self, console: Console, *, enabled: bool = True):
        self.console = console
        self.enabled = enabled

    def render(self, state: StatusState) -> Text:
        g = glyphs()
        text = Text()
        text.append(
            f"{g.PHASE} {state.phase} {state.phase_index}/{state.phase_total}",
            "devagent.accent",
        )
        text.append(" · ", "devagent.muted")
        text.append(self._todo_segment(state), "devagent.info")
        text.append(" · ", "devagent.muted")
        ctx_style = "devagent.warn" if state.context_percent >= 80 else "devagent.muted"
        text.append(f"ctx {state.context_percent}%", ctx_style)
        cost = self._cost(state)
        if cost is not None:
            text.append(" · ", "devagent.muted")
            text.append(f"${cost:.2f}", "devagent.muted")
        text.append(" · ", "devagent.muted")
        text.append(state.model, "devagent.muted")
        return text

    def live(self, label: str) -> Live:
        renderable = Text(label, style="devagent.muted") if self.enabled else Text("")
        return Live(renderable, console=self.console, transient=True, refresh_per_second=4)

    def compacted(self, before_tokens: int, after_tokens: int) -> None:
        g = glyphs()
        self.console.print(
            Text(
                f"{g.WARN} context compacted {before_tokens // 1000}k -> {after_tokens // 1000}k",
                style="devagent.warn",
            )
        )

    def _todo_segment(self, state: StatusState) -> str:
        if state.todo_total <= 0:
            return "TODO 0/0"
        done_blocks = round((state.todo_done / state.todo_total) * 5)
        g = glyphs()
        bar = g.TODO_DONE * done_blocks + g.TODO_OPEN * (5 - done_blocks)
        return f"{bar} TODO {state.todo_done}/{state.todo_total}"

    def _cost(self, state: StatusState) -> float | None:
        prices = MODEL_PRICES_PER_MTOK.get(state.model)
        if prices is None:
            return None
        input_price, output_price = prices
        return (state.input_tokens / 1_000_000) * input_price + (
            state.output_tokens / 1_000_000
        ) * output_price
