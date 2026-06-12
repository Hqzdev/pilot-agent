"""Shared pytest fixtures for PilotAgent tests."""

from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PilotAgent global home at a temporary directory for a test."""

    home = tmp_path / "home"
    monkeypatch.setenv("PILOT_AGENT_HOME", str(home))
    return home
