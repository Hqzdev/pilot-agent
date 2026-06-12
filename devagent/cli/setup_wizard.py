"""Interactive setup wizard for provider, API key, model, and deploy defaults."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from devagent.cli.auth import default_model, provider_key_env
from devagent.config.schema import update_config_values, user_config_path


def run_setup_wizard(
    *,
    provider_override: str | None = None,
    reconfigure: bool = False,
    home: Path | None = None,
    config_path: Path | None = None,
    console: Console | None = None,
) -> Path:
    del reconfigure
    console = console or Console()
    home = home or Path(os.environ.get("DEVAGENT_HOME", "~/.devagent")).expanduser()
    console.print(
        Panel(
            "DevAgent ведет проект от идеи до задеплоенного MVP.\n"
            "Настройка займет ~1 минуту, 4 вопроса.",
            title="DevAgent setup",
        )
    )
    provider = provider_override or _ask_provider()
    key_env = provider_key_env(provider)
    key = os.environ.get(key_env)
    if key:
        console.print(f"✓ Найден ${key_env}")
    else:
        key = Prompt.ask(f"Вставь API-ключ для {provider}", password=True, default="")
        if key:
            _offer_secret_storage(home, key_env, key)
        else:
            console.print(f"⚠ Ключ пропущен. Позже запусти: export {key_env}=<api-key>")
    model = Prompt.ask("Модель", default=default_model(provider))
    deploy_enabled = Confirm.ask("Деплой на Vercel (фаза deploy)?", default=True)
    updates: dict[str, object] = {
        "provider": provider,
        "model": model,
        "api_key_env": key_env,
        "phases.deploy.enabled": deploy_enabled,
    }
    path = config_path or user_config_path(home)
    update_config_values(path, updates)
    console.print(
        Panel(
            f"✓ Конфиг: {path}\n"
            f"✓ Провайдер: {provider} / {model}\n"
            f"✓ Vercel: {'включен' if deploy_enabled else 'отключен'}\n\n"
            "Запуск: cd <проект> && devagent init && devagent run\n"
            "Диагностика, если что-то не так: devagent doctor",
            title="Готово",
        )
    )
    return path


def _ask_provider() -> str:
    choice = IntPrompt.ask(
        "Выбери LLM-провайдера: 1. Anthropic  2. OpenAI  3. OpenRouter",
        default=1,
        choices=["1", "2", "3"],
    )
    return {1: "anthropic", 2: "openai", 3: "openrouter"}[choice]


def _offer_secret_storage(home: Path, env_name: str, key: str) -> None:
    choice = IntPrompt.ask(
        "Куда сохранить ключ? 1. shell rc  2. ~/.devagent/.env  3. сам разберусь",
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
        Console().print(f"Выполни: {export_line}")


def _shell_rc_path() -> Path:
    shell = Path(os.environ.get("SHELL", "")).name
    name = ".zshrc" if shell == "zsh" else ".bashrc"
    return Path.home() / name
