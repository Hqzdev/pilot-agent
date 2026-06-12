from __future__ import annotations

import copy
import json
from pathlib import Path

from pilot_agent.agent.types import CompletionResponse, Message, Role, ToolSpec
from pilot_agent.providers.base import Provider

SUMMARY_PROMPT = """Compress the agent work history into a state document.
Structure:
1. Project goal and key decisions
2. Done: created files, commands run
3. Current problem or next step
4. Errors encountered and how they were resolved
Write densely. Preserve file names and exact commands."""


class ContextManager:
    def __init__(
        self,
        provider: Provider,
        budget_ratio: float = 0.7,
        summarizer: Provider | None = None,
        session_log: Path | None = None,
    ):
        self.provider = provider
        self.budget_ratio = budget_ratio
        self.threshold = int(provider.context_window * budget_ratio)
        self.summarizer = summarizer or provider
        self.session_log = session_log

    def prepare(self, system: str, history: list[Message]) -> list[Message]:
        prepared = copy.deepcopy(history)
        before = self.provider.count_tokens(system, prepared)
        if before <= self.threshold:
            return prepared
        prepared = self._truncate_tool_results(system, prepared)
        after_level_1 = self.provider.count_tokens(system, prepared)
        if after_level_1 > self.threshold:
            prepared = self._summarize(system, prepared)
        after = self.provider.count_tokens(system, prepared)
        if after < before:
            self._write_compaction_event(before, after)
        return prepared

    def compact(self, system: str, history: list[Message]) -> list[Message]:
        prepared = copy.deepcopy(history)
        before = self.provider.count_tokens(system, prepared)
        compacted = self._summarize(system, prepared)
        after = self.provider.count_tokens(system, compacted)
        self._write_compaction_event(before, after)
        return compacted

    def replace_provider(self, provider: Provider) -> None:
        self.provider = provider
        self.summarizer = provider
        self.threshold = int(provider.context_window * self.budget_ratio)

    def _truncate_tool_results(self, system: str, history: list[Message]) -> list[Message]:
        cutoff = self._last_turn_start(history, turns=5)
        for message in history[:cutoff]:
            if message.pinned or message.role is not Role.TOOL:
                continue
            for result in message.tool_results:
                if result.truncated:
                    continue
                original_len = len(result.content)
                result.content = f"[output {original_len} chars -> {result.artifact_path}]"
                result.truncated = True
            if self.provider.count_tokens(system, history) <= self.threshold:
                break
        return history

    def _summarize(self, system: str, history: list[Message]) -> list[Message]:
        cutoff = self._last_turn_start(history, turns=3)
        prefix = history[:cutoff]
        suffix = history[cutoff:]
        pinned = [message for message in prefix if message.pinned]
        to_summarize = [message for message in prefix if not message.pinned]
        response = self.summarizer.complete(
            SUMMARY_PROMPT,
            to_summarize,
            tools=[],
            max_tokens=2048,
        )
        summary = response.message.content
        summary_message = Message(
            role=Role.USER,
            content=f"[Compressed history]\n{summary}",
            pinned=True,
        )
        return [summary_message, *pinned, *suffix]

    @staticmethod
    def _last_turn_start(history: list[Message], turns: int) -> int:
        seen = 0
        for idx in range(len(history) - 1, -1, -1):
            if history[idx].role in {Role.ASSISTANT, Role.TOOL}:
                seen += 1
            if seen >= turns * 2:
                return idx
        return 0

    def _write_compaction_event(self, before: int, after: int) -> None:
        if self.session_log is None:
            return
        self.session_log.parent.mkdir(parents=True, exist_ok=True)
        with self.session_log.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"_type": "compaction", "before_tokens": before, "after_tokens": after}
                )
                + "\n"
            )


def build_system_prompt(
    phase_prompt: str,
    state_md: str,
    skills_index: str,
    lessons: str,
    *,
    state_tokens: int = 0,
) -> str:
    state_block = f"# STATE.md\n{state_md}"
    if state_tokens > 4_000:
        state_block += "\n\nWARNING: STATE.md is too large; compress STATE.md before continuing."
    return "\n\n".join(
        [phase_prompt, state_block, skills_index, f"# Past session lessons\n{lessons}"]
    )


class StaticSummaryProvider(Provider):
    """Small test/helper provider that returns a fixed summary."""

    def __init__(self, summary: str = "summary", context_window: int = 10_000):
        super().__init__(model="static", api_key="test")
        self.summary = summary
        self._context_window = context_window

    def _complete(
        self,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        max_tokens: int = 4096,
    ) -> CompletionResponse:
        return CompletionResponse(
            message=Message(role=Role.ASSISTANT, content=self.summary),
            stop_reason="end_turn",
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    def count_tokens(self, system: str, messages: list[Message]) -> int:
        total = len(system)
        for message in messages:
            total += len(message.content)
            total += sum(len(result.content) for result in message.tool_results)
        return total

    @property
    def context_window(self) -> int:
        return self._context_window
