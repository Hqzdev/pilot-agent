from __future__ import annotations

import pytest
from typer.testing import CliRunner

from pilot_agent.agent.acceptance_blueprints import get_blueprint, list_blueprints, render_blueprint
from pilot_agent.cli import app


def test_acceptance_blueprint_catalog_has_product_checks() -> None:
    ids = {blueprint.id for blueprint in list_blueprints()}

    assert {"nightly-checks", "dependency-audit", "deploy-verification"} <= ids
    assert "scripts/run_tests.sh" in get_blueprint("nightly-checks").commands
    assert "docker compose build" in get_blueprint("deploy-verification").commands


def test_acceptance_blueprint_render_and_unknown_id() -> None:
    rendered = render_blueprint(get_blueprint("dependency-audit"))

    assert "# Dependency drift audit" in rendered
    assert "uv lock --check" in rendered
    with pytest.raises(ValueError, match="unknown acceptance blueprint"):
        get_blueprint("morning-briefing")


def test_blueprints_cli_lists_and_shows_blueprints() -> None:
    runner = CliRunner()

    list_result = runner.invoke(app, ["blueprints"])
    show_result = runner.invoke(app, ["blueprints", "show", "nightly-checks"])

    assert list_result.exit_code == 0
    assert "nightly-checks" in list_result.output
    assert show_result.exit_code == 0
    assert "Nightly local acceptance" in show_result.output
    assert "scripts/run_tests.sh" in show_result.output
