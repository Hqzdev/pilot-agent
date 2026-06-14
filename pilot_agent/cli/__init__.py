"""CLI package for the Typer app, setup wizard, auth helpers, and doctor checks."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "app":
        from pilot_agent.cli.main import app

        return app
    raise AttributeError(name)

__all__ = ["app"]
