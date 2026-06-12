from __future__ import annotations

from typer.testing import CliRunner

from devagent.cli import app


def test_cli_help_smoke() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.output
