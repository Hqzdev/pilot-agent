import pytest
from typer.testing import CliRunner

from pilot_agent.cli import app
from pilot_agent.config.schema import load_config
from pilot_agent.gateway.core import GatewayAuthorizer, GatewayEvent, authorizer_from_config
from pilot_agent.gateway.telegram import normalize_update


def test_gateway_config_and_auth_read_env_names(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PILOT_AGENT_TELEGRAM_BOT_TOKEN_ENV", "BOT_TOKEN_NAME")
    monkeypatch.setenv("PILOT_AGENT_TELEGRAM_ALLOWED_USERS", "42")

    cfg = load_config(home=tmp_path / "home", project_root=tmp_path / "project")
    auth = authorizer_from_config(cfg)

    assert cfg.gateway.telegram_bot_token_env == "BOT_TOKEN_NAME"
    assert cfg.gateway.telegram_allowed_users_env == "PILOT_AGENT_TELEGRAM_ALLOWED_USERS"
    assert cfg.gateway.allow_all_users_env == "PILOT_AGENT_GATEWAY_ALLOW_ALL_USERS"
    assert not GatewayAuthorizer(set()).is_allowed(GatewayEvent("telegram", "1", "10", "42", "hi"))
    assert auth.is_allowed(GatewayEvent("telegram", "1", "10", "42", "hi"))
    assert not auth.is_allowed(GatewayEvent("telegram", "1", "10", "99", "hi"))


def test_telegram_normalizes_text_message() -> None:
    message = {"text": "/run build", "from": {"id": 42}, "chat": {"id": -100}}

    event = normalize_update({"update_id": 100, "message": message})

    assert event == GatewayEvent("telegram", "100", "-100", "42", "/run build")
    assert normalize_update({"update_id": 101, "message": {"photo": []}}) is None


def test_gateway_cli_status_does_not_print_secret_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PILOT_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PILOT_AGENT_TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("PILOT_AGENT_TELEGRAM_ALLOWED_USERS", "42,43")
    result = CliRunner().invoke(app, ["gateway", "status"])

    assert result.exit_code == 0
    assert "PILOT_AGENT_TELEGRAM_BOT_TOKEN" in result.output
    assert "123:secret" not in result.output
