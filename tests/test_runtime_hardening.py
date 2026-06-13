from __future__ import annotations

from pathlib import Path

import pytest

from pilot_agent.agent.session_lock import ProjectSessionLock
from pilot_agent.agent.usage import SessionUsage, normalize_usage
from pilot_agent.providers.errors import classify_provider_error


class APIError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def test_provider_error_classifier_returns_fix_commands() -> None:
    auth = classify_provider_error(
        APIError(401, "invalid api key"),
        provider="anthropic",
        model="claude",
    )
    model = classify_provider_error(
        APIError(404, "model not found"),
        provider="openrouter",
        model="bad",
    )
    context = classify_provider_error(
        APIError(400, "context length too long"),
        provider="openai",
        model="gpt",
    )

    assert auth.kind == "auth"
    assert "pilot-agent auth set anthropic" in auth.fix
    assert model.kind == "model"
    assert "pilot-agent model" in model.fix
    assert context.kind == "context"
    assert "/compact" in context.fix


def test_usage_normalization_and_session_summary() -> None:
    usage = normalize_usage(
        {
            "input_tokens": 120,
            "output_tokens": 30,
            "cache_read_tokens": 20,
            "cache_write_tokens": 10,
        }
    )
    session = SessionUsage()
    session.add(usage, provider="anthropic", model="claude-sonnet-4-6")

    assert usage.input_tokens == 90
    assert usage.total_tokens == 150
    assert session.request_count == 1
    assert "estimated cost" in session.summary()


def test_project_session_lock_blocks_second_session(tmp_path: Path) -> None:
    with (
        ProjectSessionLock(tmp_path),
        pytest.raises(RuntimeError, match="already running"),
        ProjectSessionLock(tmp_path),
    ):
        pass
