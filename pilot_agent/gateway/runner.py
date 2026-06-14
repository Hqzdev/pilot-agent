from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pilot_agent.agent.context import ContextManager
from pilot_agent.agent.loop import AgentLoop, restore_phase_from_session
from pilot_agent.agent.state import init_project_state, read_session_messages, write_session_record
from pilot_agent.agent.types import Message, Role
from pilot_agent.backends import backend_from_config
from pilot_agent.cli.main import build_skill_registry, build_tool_registry
from pilot_agent.cli.ui import UI
from pilot_agent.config.schema import PilotAgentConfig
from pilot_agent.gateway.core import GatewayAdapter, GatewayAuthorizer, GatewayEvent
from pilot_agent.providers.base import from_config


class GatewayUI:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def render(self, message: Message) -> None:
        if message.content:
            self.messages.append(message.content)

    def prompt_user(self) -> str:
        return "/quit"

    def api_spinner(self) -> _Noop:
        return _Noop()

    def tool_timer(self, call: Any) -> _Noop:
        return _Noop()

    def render_tool_result(self, call: Any, result: Any, elapsed_s: float = 0) -> None:
        return None

    def phase_transition(self, phase: str, next_phase: str | None, summary: str) -> None:
        return None

    def notice(self, text: str) -> None:
        return None

    warning = notice


class _Noop:
    def __enter__(self) -> _Noop:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def add_task(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def elapsed(self) -> float:
        return 0.0


def handle_event(
    event: GatewayEvent,
    *,
    cfg: PilotAgentConfig,
    adapter: GatewayAdapter,
    authorizer: GatewayAuthorizer,
    project_root: Path,
) -> str:
    if not event.text.strip():
        return "ignored"
    if not authorizer.is_allowed(event):
        return "unauthorized"

    project_root = project_root.resolve()
    init_project_state(project_root)
    phase_name = restore_phase_from_session(project_root)
    write_session_record(
        project_root,
        Message(role=Role.USER, content=event.text, phase=phase_name),
    )

    ui = GatewayUI()
    backend = backend_from_config(cfg, project_root)
    try:
        skills = build_skill_registry()
        provider = from_config(cfg)
        registry = build_tool_registry(project_root, skills, cfg, backend=backend)
        registry.tools.pop("ask_user", None)
        loop = AgentLoop(
            project_root=project_root,
            provider=provider,
            registry=registry,
            ctx=ContextManager(
                provider,
                cfg.budget_ratio,
                session_log=project_root / ".pilot-agent/session.jsonl",
            ),
            skills=skills,
            ui=cast(UI, ui),
            phase_name=phase_name,
            history=read_session_messages(project_root),
        )
        loop.run(max_turns=cfg.gateway.max_turns_per_event)
    finally:
        backend.cleanup()

    reply = "\n\n".join(ui.messages).strip() or "Done."
    adapter.send_text(event.chat_id, reply)
    return "replied"


def run_polling(
    adapter: GatewayAdapter,
    *,
    cfg: PilotAgentConfig,
    authorizer: GatewayAuthorizer,
    project_root: Path,
    once: bool = False,
) -> None:
    while True:
        for event in adapter.poll_events():
            handle_event(
                event,
                cfg=cfg,
                adapter=adapter,
                authorizer=authorizer,
                project_root=project_root,
            )
        if once:
            return
