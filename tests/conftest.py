"""Shared pytest fixtures for DevAgent tests."""

from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DevAgent global home at a temporary directory for a test."""

    home = tmp_path / "home"
    monkeypatch.setenv("DEVAGENT_HOME", str(home))
    return home
