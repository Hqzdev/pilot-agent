"""Interactive setup wizard for provider, API key, model, and deploy defaults."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from rich.console import Console

from pilot_agent.cli.auth import default_model, provider_key_env
from pilot_agent.cli.ui.components import create_console, panel
from pilot_agent.cli.ui.input import PilotAgentInput
from pilot_agent.cli.ui.theme import glyphs
from pilot_agent.config.credentials import set_credential
from pilot_agent.config.schema import recommended_label, update_config_values, user_config_path


def run_setup_wizard(
    *,
    provider_override: str | None = None,
    reconfigure: bool = False,
    home: Path | None = None,
    config_path: Path | None = None,
    console: Console | None = None,
) -> Path:
    del reconfigure
    console = console or create_console()
    home = home or Path(os.environ.get("PILOT_AGENT_HOME", "~/.pilot-agent")).expanduser()
    prompt = PilotAgentInput(history_path=home / "input_history")
    g = glyphs()
    console.print(
        panel(
            "Pilot Agent guides a project from idea to deployed MVP.\n"
            "Setup takes about 1 minute and 6 questions.",
            title="Pilot Agent setup",
        )
    )
    provider = provider_override or _ask_provider(prompt, console)
    key_env = provider_key_env(provider)
    key = os.environ.get(key_env)
    if key:
        console.print(f"{g.OK} Found ${key_env}", style="pilot_agent.ok")
    else:
        _step(console, 2, 6, "API key")
        key = prompt.prompt(f"Paste the API key for {provider}", password=True, default="")
        if key:
            _offer_secret_storage(home, key_env, key, prompt)
        else:
            console.print(
                f"{g.WARN} Key skipped. Later run: export {key_env}=<api-key>",
                style="pilot_agent.warn",
            )
    _step(console, 3, 6, "Model")
    model = prompt.prompt("Model", default=default_model(provider))
    backend = _ask_backend(prompt, console)
    web_search_enabled, web_search_provider = _ask_web_search(prompt, console, home)
    _step(console, 6, 6, "Deploy")
    deploy_enabled = prompt.confirm("Deploy to Vercel during the deploy phase?", default=True)
    updates: dict[str, object] = {
        "provider": provider,
        "model": model,
        "api_key_env": key_env,
        "backend": backend,
        "tools.web_search.enabled": web_search_enabled,
        "tools.web_search.provider": web_search_provider,
        "phases.deploy.enabled": deploy_enabled,
        "tools.deploy.enabled": deploy_enabled,
    }
    path = config_path or user_config_path(home)
    update_config_values(path, updates)
    console.print(
        panel(
            f"{g.OK} Config: {path}\n"
            f"{g.OK} Provider: {provider} / {model}\n"
            f"{g.OK} Backend: {backend}\n"
            f"{g.OK} Web search: {'enabled' if web_search_enabled else 'disabled'}\n"
            f"{g.OK} Vercel: {'enabled' if deploy_enabled else 'disabled'}\n\n"
            "Run: cd <project> && pilot-agent init && pilot-agent run\n"
            "Diagnostics: pilot-agent doctor",
            title="Ready",
            border_style="pilot_agent.ok",
        )
    )
    return path


def _step(console: Console, idx: int, total: int, title: str) -> None:
    console.print(f"{glyphs().PHASE} Step {idx}/{total} · {title}", style="pilot_agent.accent")


def _ask_provider(prompt: PilotAgentInput, console: Console) -> str:
    _step(console, 1, 6, "Provider")
    choice = prompt.ask_int(
        "Choose an LLM provider: "
        f"1. {recommended_label('provider')}  2. OpenAI - broad model catalog  "
        "3. OpenRouter - 200+ models with one key",
        default=1,
        choices=["1", "2", "3"],
    )
    return {1: "anthropic", 2: "openai", 3: "openrouter"}[choice]


def _ask_backend(prompt: PilotAgentInput, console: Console) -> str:
    _step(console, 4, 6, "Execution backend")
    if _docker_available():
        choice = prompt.ask_int(
            "Where should agent commands run? "
            f"1. {recommended_label('backend')}  "
            "2. Local - faster, but bash runs directly on your machine",
            default=1,
            choices=["1", "2"],
        )
        return {1: "docker", 2: "local"}[choice]
    choice = prompt.ask_int(
        "Docker was not found. 1. Install Docker and rerun setup  "
        "2. Local - no isolation",
        default=1,
        choices=["1", "2"],
    )
    if choice == 1:
        console.print("Install Docker Desktop: https://docs.docker.com/get-docker/")
        raise KeyboardInterrupt
    return "local"


def _ask_web_search(
    prompt: PilotAgentInput,
    console: Console,
    home: Path,
) -> tuple[bool, str]:
    _step(console, 5, 6, "Web search")
    enabled = prompt.confirm(
        "Enable web_search? You can configure it later with pilot-agent tools.",
        default=True,
    )
    if not enabled:
        return False, "tavily"
    choice = prompt.ask_int(
        "Search provider: "
        f"1. {recommended_label('tools.web_search.provider')}  "
        "2. Brave - strong web index, key required  "
        "3. SearxNG - self-hosted, no key required",
        default=1,
        choices=["1", "2", "3"],
    )
    provider = {1: "tavily", 2: "brave", 3: "searxng"}[choice]
    if provider != "searxng":
        env_name = f"{provider.upper()}_API_KEY"
        if not os.environ.get(env_name):
            key = prompt.prompt(f"{env_name} key (Enter to skip)", password=True, default="")
            if key:
                set_credential(provider, key, home)
            else:
                enabled = False
                console.print(
                    f"{glyphs().WARN} web_search left disabled: missing {env_name}",
                    style="pilot_agent.warn",
                )
    return enabled, provider


def _offer_secret_storage(
    home: Path,
    env_name: str,
    key: str,
    prompt: PilotAgentInput,
) -> None:
    choice = prompt.ask_int(
        "Where should the key be stored? 1. shell rc  2. ~/.pilot-agent/.env  3. I will handle it",
        default=2,
        choices=["1", "2", "3"],
    )
    export_line = f"export {env_name}={key}"
    if choice == 1:
        rc_path = _shell_rc_path()
        with rc_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{export_line}\n")
    elif choice == 2:
        home.mkdir(parents=True, exist_ok=True)
        env_path = home / ".env"
        with env_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{export_line}\n")
        env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    else:
        create_console().print(f"Run: {export_line}", style="pilot_agent.accent")


def _shell_rc_path() -> Path:
    shell = Path(os.environ.get("SHELL", "")).name
    name = ".zshrc" if shell == "zsh" else ".bashrc"
    return Path.home() / name


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
