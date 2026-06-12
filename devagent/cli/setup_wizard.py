"""Interactive setup wizard for provider, API key, model, and deploy defaults."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from rich.console import Console

from devagent.cli.auth import default_model, provider_key_env
from devagent.cli.ui.components import create_console, panel
from devagent.cli.ui.input import DevAgentInput
from devagent.cli.ui.theme import glyphs
from devagent.config.credentials import set_credential
from devagent.config.schema import recommended_label, update_config_values, user_config_path


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
    home = home or Path(os.environ.get("DEVAGENT_HOME", "~/.devagent")).expanduser()
    prompt = DevAgentInput(history_path=home / "input_history")
    g = glyphs()
    console.print(
        panel(
            "DevAgent ведет проект от идеи до задеплоенного MVP.\n"
            "Настройка займет ~1 минуту, 6 вопросов.",
            title="DevAgent setup",
        )
    )
    provider = provider_override or _ask_provider(prompt, console)
    key_env = provider_key_env(provider)
    key = os.environ.get(key_env)
    if key:
        console.print(f"{g.OK} Найден ${key_env}", style="devagent.ok")
    else:
        _step(console, 2, 6, "API-ключ")
        key = prompt.prompt(f"Вставь API-ключ для {provider}", password=True, default="")
        if key:
            _offer_secret_storage(home, key_env, key, prompt)
        else:
            console.print(
                f"{g.WARN} Ключ пропущен. Позже запусти: export {key_env}=<api-key>",
                style="devagent.warn",
            )
    _step(console, 3, 6, "Модель")
    model = prompt.prompt("Модель", default=default_model(provider))
    backend = _ask_backend(prompt, console)
    web_search_enabled, web_search_provider = _ask_web_search(prompt, console, home)
    _step(console, 6, 6, "Деплой")
    deploy_enabled = prompt.confirm("Деплой на Vercel (фаза deploy)?", default=True)
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
            f"{g.OK} Конфиг: {path}\n"
            f"{g.OK} Провайдер: {provider} / {model}\n"
            f"{g.OK} Backend: {backend}\n"
            f"{g.OK} Web search: {'включен' if web_search_enabled else 'отключен'}\n"
            f"{g.OK} Vercel: {'включен' if deploy_enabled else 'отключен'}\n\n"
            "Запуск: cd <проект> && devagent init && devagent run\n"
            "Диагностика, если что-то не так: devagent doctor",
            title="Готово",
            border_style="devagent.ok",
        )
    )
    return path


def _step(console: Console, idx: int, total: int, title: str) -> None:
    console.print(f"{glyphs().PHASE} Шаг {idx}/{total} · {title}", style="devagent.accent")


def _ask_provider(prompt: DevAgentInput, console: Console) -> str:
    _step(console, 1, 6, "Провайдер")
    choice = prompt.ask_int(
        "Выбери LLM-провайдера: "
        f"1. {recommended_label('provider')}  2. OpenAI — широкий каталог моделей  "
        "3. OpenRouter — 200+ моделей одним ключом",
        default=1,
        choices=["1", "2", "3"],
    )
    return {1: "anthropic", 2: "openai", 3: "openrouter"}[choice]


def _ask_backend(prompt: DevAgentInput, console: Console) -> str:
    _step(console, 4, 6, "Бэкенд исполнения")
    if _docker_available():
        choice = prompt.ask_int(
            "Где исполнять команды агента? "
            f"1. {recommended_label('backend')}  "
            "2. Локально — быстрее, но bash идет прямо на твоей машине",
            default=1,
            choices=["1", "2"],
        )
        return {1: "docker", 2: "local"}[choice]
    choice = prompt.ask_int(
        "Docker не найден. 1. Установить Docker и перезапустить setup  "
        "2. Локально — без изоляции",
        default=1,
        choices=["1", "2"],
    )
    if choice == 1:
        console.print("Install Docker Desktop: https://docs.docker.com/get-docker/")
        raise KeyboardInterrupt
    return "local"


def _ask_web_search(
    prompt: DevAgentInput,
    console: Console,
    home: Path,
) -> tuple[bool, str]:
    _step(console, 5, 6, "Web search")
    enabled = prompt.confirm(
        "Включить web_search? Можно настроить позже через devagent tools.",
        default=True,
    )
    if not enabled:
        return False, "tavily"
    choice = prompt.ask_int(
        "Провайдер поиска: "
        f"1. {recommended_label('tools.web_search.provider')}  "
        "2. Brave — хороший web index, нужен ключ  "
        "3. SearxNG — self-hosted, ключ не нужен",
        default=1,
        choices=["1", "2", "3"],
    )
    provider = {1: "tavily", 2: "brave", 3: "searxng"}[choice]
    if provider != "searxng":
        env_name = f"{provider.upper()}_API_KEY"
        if not os.environ.get(env_name):
            key = prompt.prompt(f"Ключ {env_name} (Enter — пропустить)", password=True, default="")
            if key:
                set_credential(provider, key, home)
            else:
                enabled = False
                console.print(
                    f"{glyphs().WARN} web_search оставлен выключенным: нет ключа {env_name}",
                    style="devagent.warn",
                )
    return enabled, provider


def _offer_secret_storage(
    home: Path,
    env_name: str,
    key: str,
    prompt: DevAgentInput,
) -> None:
    choice = prompt.ask_int(
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
        create_console().print(f"Выполни: {export_line}", style="devagent.accent")


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
