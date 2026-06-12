"""Interactive setup wizard for provider, API key, model, and deploy defaults."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from pilot_agent.cli.auth import (
    default_model,
    list_models,
    provider_key_env,
    validate_provider_key,
)
from pilot_agent.cli.ui.components import create_console, panel
from pilot_agent.cli.ui.input import PilotAgentInput
from pilot_agent.cli.ui.theme import glyphs
from pilot_agent.config.credentials import (
    credentials_path,
    mask_secret,
    resolve_credential,
    service_env_var,
    set_credential,
)
from pilot_agent.config.schema import (
    PilotAgentConfig,
    load_config,
    update_config_values,
    user_config_path,
)


def run_setup_wizard(
    *,
    provider_override: str | None = None,
    reconfigure: bool = False,
    home: Path | None = None,
    config_path: Path | None = None,
    console: Console | None = None,
) -> Path:
    console = console or create_console()
    home = home or Path(os.environ.get("PILOT_AGENT_HOME", "~/.pilot-agent")).expanduser()
    current = _current_config(home, config_path) if reconfigure else None
    prompt = PilotAgentInput(history_path=home / "input_history")
    g = glyphs()
    console.print(
        panel(
            "Pilot Agent guides a project from idea to deployed MVP.\n"
            "Setup takes about 1 minute and 4 questions.",
            title="Pilot Agent setup",
        )
    )
    provider = provider_override or _ask_provider(prompt, console, current)
    key_env = provider_key_env(provider)
    _step(console, 2, 4, "API key")
    _ensure_provider_key(provider, key_env, prompt, console, home, current)
    _step(console, 3, 4, "Model")
    model_default = (
        current.model if current and current.provider == provider else default_model(provider)
    )
    model = _ask_model(prompt, console, provider, model_default, home)
    _step(console, 4, 4, "Deploy")
    deploy_default = current.phases.deploy.enabled if current else True
    deploy_enabled = prompt.confirm(
        "Deploy to Vercel during the deploy phase?",
        default=deploy_default,
    )
    if deploy_enabled:
        _ensure_vercel_token(prompt, console, home)

    updates: dict[str, object] = {
        "provider": provider,
        "model": model,
        "api_key_env": key_env,
        "phases.deploy.enabled": deploy_enabled,
        "tools.deploy.enabled": deploy_enabled,
    }
    path = config_path or user_config_path(home)
    update_config_values(path, updates)
    vercel_state = "configured" if resolve_credential("vercel", home).value else "will ask later"
    console.print(
        panel(
            f"{g.OK} Config: {path}\n"
            f"{g.OK} Provider: {provider} / {model}\n"
            f"{g.OK} Vercel: {vercel_state if deploy_enabled else 'disabled'}\n\n"
            "Run: cd <project> && pilot-agent init && pilot-agent run\n"
            "Diagnostics: pilot-agent doctor",
            title="Ready",
            border_style="pilot_agent.ok",
        )
    )
    return path


def _current_config(home: Path, config_path: Path | None) -> PilotAgentConfig | None:
    try:
        return load_config(home=home, config_path=config_path)
    except Exception:
        return None


def _step(console: Console, idx: int, total: int, title: str) -> None:
    console.print(f"{glyphs().PHASE} Step {idx}/{total} · {title}", style="pilot_agent.accent")


def _ask_provider(
    prompt: PilotAgentInput,
    console: Console,
    current: PilotAgentConfig | None,
) -> str:
    _step(console, 1, 4, "Provider")
    default = {"anthropic": 0, "openai": 1, "openrouter": 2}.get(
        current.provider if current else "anthropic",
        0,
    )
    return prompt.select(
        "Choose an LLM provider:",
        [
            ("anthropic", "Anthropic (recommended - best tool calling)"),
            ("openai", "OpenAI"),
            ("openrouter", "OpenRouter (200+ models, one key)"),
        ],
        default=default,
    )


def _ask_model(
    prompt: PilotAgentInput,
    console: Console,
    provider: str,
    default: str,
    home: Path,
) -> str:
    models = list_models(
        provider,
        api_key=resolve_credential(provider, home, env_name=provider_key_env(provider)).value,
    )
    choices = [
        (model.name, _model_label(model.name, model.context_window))
        for model in models[:20]
    ]
    choices.append(("__custom__", "Custom model..."))
    default_index = next(
        (idx for idx, (name, _) in enumerate(choices) if name == default),
        0,
    )
    selected = prompt.select("Choose a model:", choices, default=default_index)
    if selected == "__custom__":
        return prompt.prompt("Model", default=default)
    console.print(f"{glyphs().OK} Model: {selected}", style="pilot_agent.ok")
    return selected


def _model_label(name: str, context_window: int) -> str:
    if context_window >= 1_000_000:
        context = f"{context_window // 1_000_000}M"
    else:
        context = f"{context_window // 1_000}k"
    return f"{name} ({context} context)"


def _ensure_provider_key(
    provider: str,
    key_env: str,
    prompt: PilotAgentInput,
    console: Console,
    home: Path,
    current: PilotAgentConfig | None,
) -> None:
    g = glyphs()
    resolved = resolve_credential(provider, home, env_name=key_env)
    if resolved.source == "env":
        console.print(
            f"{g.OK} Using key from environment (${resolved.env_name})",
            style="pilot_agent.ok",
        )
        return
    if resolved.source == "credentials":
        replace = prompt.confirm(
            f"Saved key found ({mask_secret(resolved.value)}). Replace it?",
            default=False,
        )
        if not replace:
            return
    link = _key_url(provider)
    if link:
        console.print(f"Get a key: {link}", style="pilot_agent.dim")
    for attempt in range(1, 4):
        key = prompt.prompt(f"{provider} API key", password=True, default="")
        if not key:
            console.print(
                f"{g.WARN} Key skipped. Later run: pilot-agent auth set {provider}",
                style="pilot_agent.warn",
            )
            return
        validation = validate_provider_key(
            provider,
            key,
            base_url=current.base_url if current else None,
            model=current.model if current and current.provider == provider else None,
        )
        if validation.status == "fail" and attempt < 3:
            console.print(
                f"{g.WARN} API rejected the key: {validation.details}",
                style="pilot_agent.warn",
            )
            if not prompt.confirm("Try entering the key again?", default=True):
                break
            continue
        if validation.status == "fail":
            if not prompt.confirm("Continue without validation?", default=False):
                continue
        elif validation.status == "warn":
            console.print(f"{g.WARN} {validation.details}", style="pilot_agent.warn")
        set_credential(provider, key, home)
        console.print(
            f"{g.OK} Saved to {credentials_path(home)} (only readable by you)",
            style="pilot_agent.ok",
        )
        return


def _ensure_vercel_token(prompt: PilotAgentInput, console: Console, home: Path) -> None:
    g = glyphs()
    resolved = resolve_credential("vercel", home, env_name=service_env_var("vercel"))
    if resolved.source == "env":
        console.print(
            f"{g.OK} Using Vercel token from ${resolved.env_name}",
            style="pilot_agent.ok",
        )
        return
    if resolved.source == "credentials":
        console.print(
            f"{g.OK} Vercel token saved ({mask_secret(resolved.value)})",
            style="pilot_agent.ok",
        )
        return
    console.print("Create a token: https://vercel.com/account/tokens", style="pilot_agent.dim")
    token = prompt.prompt("Vercel token (Enter to skip)", password=True, default="")
    if token:
        set_credential("vercel", token, home)
        console.print(
            f"{g.OK} Saved Vercel token to {credentials_path(home)}",
            style="pilot_agent.ok",
        )
    else:
        console.print(
            f"{g.WARN} Deploy phase will ask for Vercel credentials later",
            style="pilot_agent.warn",
        )


def _key_url(provider: str) -> str:
    return {
        "anthropic": "https://console.anthropic.com/settings/keys",
        "openai": "https://platform.openai.com/api-keys",
        "openrouter": "https://openrouter.ai/keys",
    }.get(provider, "")


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    result = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0
