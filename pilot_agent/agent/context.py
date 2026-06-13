from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from pilot_agent.agent.safety import redact_sensitive_text
from pilot_agent.agent.types import CompletionResponse, Message, Role, ToolResult, ToolSpec
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
        self._ineffective_compactions = 0

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
            if after > before * 0.9:
                self._ineffective_compactions += 1
            else:
                self._ineffective_compactions = 0
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
        seen_tool_outputs: dict[str, str] = {}
        for message in reversed(history[:cutoff]):
            if message.role is not Role.TOOL:
                continue
            for result in message.tool_results:
                key = str(hash(result.content))
                if len(result.content) > 200 and key in seen_tool_outputs:
                    result.content = (
                        "[duplicate tool output omitted; same content as "
                        f"{seen_tool_outputs[key]}]"
                    )
                    result.truncated = True
                else:
                    seen_tool_outputs[key] = result.artifact_path or result.tool_call_id
        for message in history[:cutoff]:
            if message.pinned or message.role is not Role.TOOL:
                continue
            for result in message.tool_results:
                if result.truncated:
                    continue
                original_len = len(result.content)
                result.content = self._tool_result_summary(result, original_len)
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
        try:
            response = self.summarizer.complete(
                SUMMARY_PROMPT,
                to_summarize,
                tools=[],
                max_tokens=2048,
            )
            summary = response.message.content
        except Exception as exc:
            summary = self._fallback_summary(to_summarize, reason=str(exc))
        summary_message = Message(
            role=Role.USER,
            content=f"[Compressed history]\n{summary}",
            pinned=True,
        )
        return [summary_message, *pinned, *suffix]

    def _tool_result_summary(self, result: ToolResult, original_len: int) -> str:
        artifact = result.artifact_path or "(artifact unavailable)"
        first = result.content.strip().splitlines()[0] if result.content.strip() else ""
        first = redact_sensitive_text(first)
        if len(first) > 180:
            first = first[:177] + "..."
        suffix = f"; first line: {first}" if first else ""
        return f"[output {original_len} chars -> {artifact}{suffix}]"

    def _fallback_summary(self, messages: list[Message], *, reason: str) -> str:
        user_asks: list[str] = []
        assistant_actions: list[str] = []
        tool_results: list[str] = []
        paths: list[str] = []
        errors: list[str] = []
        for message in messages:
            content = redact_sensitive_text(message.content).strip()
            if message.role is Role.USER and content:
                user_asks.append(_compact(content))
            if message.role is Role.ASSISTANT:
                if content:
                    assistant_actions.append(_compact(content))
                for call in message.tool_calls:
                    compact_args = _compact(json.dumps(call.arguments, default=str))
                    assistant_actions.append(f"called {call.name}({compact_args})")
                    _collect_paths(call.arguments, paths)
            if message.role is Role.TOOL:
                for result in message.tool_results:
                    line = _compact(result.content)
                    tool_results.append(f"{result.tool_call_id}: {line}")
                    if result.is_error:
                        errors.append(line)
                    if result.artifact_path:
                        paths.append(result.artifact_path)
        return "\n".join(
            [
                "Summary generated locally because LLM compaction failed.",
                f"Reason: {redact_sensitive_text(reason)}",
                "",
                "Recent user asks:",
                *[f"- {item}" for item in user_asks[-6:]],
                "Assistant/tool actions:",
                *[f"- {item}" for item in assistant_actions[-10:]],
                "Tool results:",
                *[f"- {item}" for item in tool_results[-10:]],
                "Relevant paths:",
                *[f"- {item}" for item in _dedupe(paths)[-12:]],
                "Errors/blockers:",
                *[f"- {item}" for item in errors[-6:]],
            ]
        )

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
                    {
                        "_type": "compaction",
                        "before_tokens": before,
                        "after_tokens": after,
                        "saved_tokens": max(0, before - after),
                        "ineffective_count": self._ineffective_compactions,
                    }
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


def _compact(text: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", redact_sensitive_text(text)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 15].rstrip() + " ...[truncated]"


def _collect_paths(value: object, output: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "workdir", "file", "file_path", "output_path"} and isinstance(
                item,
                str,
            ):
                output.append(item)
            _collect_paths(item, output)
    elif isinstance(value, list):
        for item in value:
            _collect_paths(item, output)
    elif isinstance(value, str):
        for match in re.findall(r"(?:\.{0,2}/)?[\w.-]+(?:/[\w.@-]+)+", value):
            output.append(match)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
