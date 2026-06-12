"""Typer CLI entry point for Pilot Agent commands and first-run preflight."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from importlib import metadata
from operator import methodcaller
from pathlib import Path
from typing import Annotated

import typer

from pilot_agent.agent.context import ContextManager
from pilot_agent.agent.loop import AgentLoop, restore_phase_from_session
from pilot_agent.agent.phases import PHASES
from pilot_agent.agent.state import (
    append_reentry_request,
    init_project_state,
    read_session_messages,
    session_path,
    state_path,
    write_session_record,
)
from pilot_agent.agent.types import Message, Role
from pilot_agent.backends import ExecutionBackend, backend_from_config
from pilot_agent.cli.auth import PROVIDERS, list_models, provider_key_env, validate_provider_key
from pilot_agent.cli.doctor import checks_to_json, has_failures, run_doctor_checks
from pilot_agent.cli.setup_wizard import run_setup_wizard
from pilot_agent.cli.ui import UI
from pilot_agent.cli.ui.banner import BannerState, render_banner
from pilot_agent.cli.ui.components import create_console, simple_table
from pilot_agent.cli.ui.input import PilotAgentInput
from pilot_agent.config.credentials import (
    credential_services,
    credentials_permissions,
    credentials_path,
    get_credential,
    mask_secret,
    remove_credential,
    resolve_credential,
    service_env_var,
    set_credential,
)
from pilot_agent.config.schema import (
    RECOMMENDED,
    PilotAgentConfig,
    config_value,
    default_home,
    flatten_config,
    load_config,
    set_config_value,
    update_config_values,
    user_config_path,
)
from pilot_agent.providers.base import Provider, from_config
from pilot_agent.skills.registry import SkillRegistry
from pilot_agent.tools.ask_user import AskUserTool
from pilot_agent.tools.base import ToolRegistry
from pilot_agent.tools.bash import BashTool
from pilot_agent.tools.file_ops import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from pilot_agent.tools.phase_tools import CompletePhaseTool
from pilot_agent.tools.run_check import RunAndCheckTool
from pilot_agent.tools.search_providers import provider_from_config
from pilot_agent.tools.skill_tools import LoadSkillTool, SaveSkillTool
from pilot_agent.tools.web_fetch import WebFetchTool
from pilot_agent.tools.web_search import WebSearchTool

app = typer.Typer(help="Pilot Agent local MVP agent.")
skills_app = typer.Typer(help="Manage skills.")
config_app = typer.Typer(help="Manage configuration.")
lessons_app = typer.Typer(help="Manage lessons.")
sessions_app = typer.Typer(help="Manage sessions.")
auth_app = typer.Typer(help="Manage credentials.")
sandbox_app = typer.Typer(help="Manage Docker sandbox image and containers.")
app.add_typer(skills_app, name="skills")
app.add_typer(config_app, name="config")
app.add_typer(lessons_app, name="lessons")
app.add_typer(sessions_app, name="sessions")
app.add_typer(auth_app, name="auth")
app.add_typer(sandbox_app, name="sandbox")
console = create_console()
INIT_PATH_ARGUMENT = typer.Argument(Path("."), help="Project path to initialize.")
GLOBAL_PROVIDER: str | None = None
GLOBAL_MODEL: str | None = None
GLOBAL_CONFIG_PATH: Path | None = None


def emit(*objects: object) -> None:
    methodcaller("print", *objects)(console)


@app.callback()
def root_options(
    provider: Annotated[str | None, typer.Option("--provider", help="Provider override.")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model override.")] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Alternative config path."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug log to stderr.")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable terminal colors.")] = False,
) -> None:
    global GLOBAL_CONFIG_PATH, GLOBAL_MODEL, GLOBAL_PROVIDER
    GLOBAL_PROVIDER = provider
    GLOBAL_MODEL = model
    GLOBAL_CONFIG_PATH = config
    if verbose:
        os.environ["PILOT_AGENT_VERBOSE"] = "1"
    if no_color:
        os.environ["NO_COLOR"] = "1"
        console.no_color = True


def load_config_or_exit(provider: str | None = None, model: str | None = None) -> PilotAgentConfig:
    try:
        return load_config(
            provider=provider or GLOBAL_PROVIDER,
            model=model or GLOBAL_MODEL,
            config_path=GLOBAL_CONFIG_PATH,
        )
    except Exception as exc:
        emit(f"Error: invalid config: {exc}")
        raise typer.Exit(1) from None


def resolve_key_or_exit(cfg: PilotAgentConfig) -> None:
    try:
        cfg.resolve_key()
    except RuntimeError as exc:
        emit(f"Error: {exc}")
        raise typer.Exit(1) from None


def render_config(cfg: PilotAgentConfig) -> None:
    table = simple_table("key", "value", "source")
    flat = flatten_config(cfg)
    for key in sorted(flat):
        value = flat[key]
        display = json.dumps(value) if isinstance(value, bool | int | float) else str(value)
        table.add_row(key, display, cfg.sources.get(key, "defaults"))
    resolved = resolve_credential(cfg.provider, default_home(), env_name=cfg.api_key_env)
    table.add_row(
        "api_key_present",
        str(bool(resolved.value)).lower(),
        resolved.source,
    )
    emit(table)


def build_skill_registry() -> SkillRegistry:
    home = default_home()
    builtin = Path(__file__).parents[1] / "skills" / "builtin"
    return SkillRegistry([builtin, home / "skills"], home=home)


def build_tool_registry(
    project_root: Path,
    skills: SkillRegistry,
    cfg: PilotAgentConfig,
    backend: ExecutionBackend | None = None,
) -> ToolRegistry:
    backend = backend or backend_from_config(cfg, project_root)
    tools = [
        AskUserTool(),
        BashTool(project_root, backend=backend),
        ReadFileTool(project_root),
        WriteFileTool(project_root),
        EditFileTool(project_root),
        ListFilesTool(project_root),
        RunAndCheckTool(project_root, backend=backend),
        LoadSkillTool(skills),
        SaveSkillTool(skills),
        CompletePhaseTool(),
    ]
    if cfg.tools.web_search.enabled:
        try:
            search = provider_from_config(
                cfg.tools.web_search.provider,
                api_key=get_credential(cfg.tools.web_search.provider, default_home()),
                searxng_url=cfg.tools.web_search.searxng_url,
            )
            tools.append(WebSearchTool(search, cfg.tools.web_search.max_results))
        except ValueError:
            pass
    if cfg.tools.web_fetch.enabled:
        tools.append(WebFetchTool())
    for tool in tools:
        tool.timeout_s = cfg.tool_timeout_s
    return ToolRegistry(tools, project_root)


def run_loop(cfg: PilotAgentConfig) -> None:
    project_root = Path(".").resolve()
    init_project_state(project_root)
    skills = build_skill_registry()
    provider = from_config(cfg)
    backend = backend_from_config(cfg, project_root)
    registry = build_tool_registry(project_root, skills, cfg, backend=backend)
    session_log = project_root / ".pilot-agent" / "session.jsonl"
    phase_name = restore_phase_from_session(project_root)
    history = read_session_messages(project_root)
    skill_names = sorted(skills.records)
    ui = UI(
        console=console,
        color=cfg.ui.color,
        show_status=cfg.ui.show_token_counter,
        history_path=default_home() / "input_history",
        skill_names=skill_names,
    )
    render_banner(
        console,
        BannerState(
            version=_package_version(),
            provider=cfg.provider,
            model=cfg.model,
            project_root=project_root,
            phase=phase_name or "complete",
            lessons_count=_lesson_count(default_home()),
            skills_count=len(skill_names),
            resumed=bool(history),
            turns=len(history),
        ),
    )
    try:
        loop = AgentLoop(
            project_root=project_root,
            provider=provider,
            registry=registry,
            ctx=ContextManager(provider, cfg.budget_ratio, session_log=session_log),
            skills=skills,
            ui=ui,
            phase_name=phase_name,
            history=history,
            model_switcher=_make_model_switcher(cfg),
        )
        loop.run(max_turns=cfg.max_turns)
    finally:
        backend.cleanup()


def _make_model_switcher(cfg: PilotAgentConfig) -> Callable[[str], Provider]:
    def switch(target: str) -> Provider:
        if ":" in target:
            provider_name, model_name = target.split(":", 1)
        else:
            provider_name, model_name = cfg.provider, target
        api_key_env = provider_key_env(provider_name)
        update_config_values(
            _config_write_path(),
            {
                "provider": provider_name,
                "model": model_name,
                "api_key_env": api_key_env,
            },
        )
        return from_config(load_config())

    return switch


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ensure_config_for_run() -> None:
    path = _config_write_path()
    if path.exists():
        return
    if not _interactive():
        return
    if PilotAgentInput().confirm("Config not found. Run pilot-agent setup?", default=True):
        run_setup_wizard(config_path=GLOBAL_CONFIG_PATH)
        return
    emit("Run: pilot-agent setup")
    raise typer.Exit(1)


def _ensure_project_for_run(*, resume_mode: bool = False) -> None:
    root = Path(".").resolve()
    if not (root / ".pilot-agent").exists():
        if _interactive() and PilotAgentInput().confirm(
            f"Project is not initialized. Run pilot-agent init here ({root})?",
            default=True,
        ):
            init_project_state(root)
        else:
            emit("Project is not initialized. Run: pilot-agent init")
            raise typer.Exit(1)
    if resume_mode:
        return
    session = session_path(root)
    if not _interactive() or not session.exists() or session.stat().st_size == 0:
        return
    phase = restore_phase_from_session(root)
    if phase is None:
        return
    choice = PilotAgentInput().prompt(
        f"Found an unfinished session (phase {phase}). [R]esume / [N]ew / [A]bort?",
        choices=["R", "N", "A", "r", "n", "a"],
        default="R",
    ).lower()
    if choice == "a":
        raise typer.Exit(1)
    if choice == "n":
        backup = session.with_suffix(".jsonl.bak")
        session.replace(backup)
        session.touch()
        emit(f"previous session moved to {backup}")


def _handle_reentry_for_completed_project() -> None:
    root = Path(".").resolve()
    if restore_phase_from_session(root) is not None or not _interactive():
        return
    prompt = PilotAgentInput(history_path=default_home() / "input_history")
    choice = prompt.ask_int(
        "Pipeline is complete. Choose next work: 1. Improvement  2. Bug fix",
        default=1,
        choices=["1", "2"],
    )
    kind = "bugfix" if choice == 2 else "improvement"
    description = prompt.prompt(
        "Describe the bug to reproduce" if kind == "bugfix" else "Describe the improvement",
        default="",
    )
    if not description.strip():
        emit("No re-entry request provided; project remains complete")
        raise typer.Exit(0)
    append_reentry_request(root, kind=kind, description=description)
    user_content = (
        f"Re-entry bug fix request: {description.strip()}"
        if kind == "bugfix"
        else f"Re-entry improvement request: {description.strip()}"
    )
    write_session_record(root, {"_type": "reentry", "kind": kind, "description": description})
    write_session_record(root, Message(role=Role.USER, content=user_content, phase="coding"))
    write_session_record(root, {"_type": "phase_change", "from": None, "to": "coding"})
    emit(f"added {kind} request to STATE.md and resumed coding")


@app.command()
def init(path: Path = INIT_PATH_ARGUMENT) -> None:
    state = init_project_state(path.resolve())
    emit(f"initialized {state.parent}")


@app.command()
def setup(
    provider: str | None = typer.Option(None, "--provider"),
    reconfigure: bool = typer.Option(False, "--reconfigure"),
) -> None:
    try:
        if provider is not None:
            provider_key_env(provider)
        run_setup_wizard(
            provider_override=provider,
            reconfigure=reconfigure,
            config_path=GLOBAL_CONFIG_PATH,
        )
    except Exception as exc:
        emit(f"Error: setup failed: {exc}")
        raise typer.Exit(1) from None


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json")) -> None:
    checks = run_doctor_checks(project_root=Path(".").resolve())
    if json_output:
        typer.echo(checks_to_json(checks))
    else:
        table = simple_table("status", "check", "details", "fix")
        symbols = {"pass": "✓", "warn": "⚠", "fail": "✗"}
        for check in checks:
            table.add_row(symbols[check.status], check.name, check.details, check.fix or "")
        emit(table)
        if has_failures(checks):
            emit("Fix each ✗ and rerun pilot-agent doctor")
    if has_failures(checks):
        raise typer.Exit(1)


@app.command()
def version() -> None:
    package_version = _package_version()
    commit = _git_commit()
    emit(
        f"pilot-agent {package_version}\n"
        f"commit {commit}\n"
        f"python {sys.version.split()[0]}\n"
        f"platform {platform.platform()}"
    )


@app.command()
def update() -> None:
    source = Path.home() / ".pilot-agent-src"
    if source.exists():
        old = _git_commit(source)
        subprocess.run(["git", "-C", str(source), "pull"], check=False)
        subprocess.run(
            ["docker", "compose", "-f", str(source / "docker-compose.yml"), "build"],
            check=False,
        )
        new = _git_commit(source)
        emit(f"updated docker install: {old} -> {new}")
        if old != new:
            log = subprocess.run(
                ["git", "-C", str(source), "log", "--oneline", f"{old}..{new}"],
                text=True,
                capture_output=True,
                check=False,
            )
            if log.stdout.strip():
                emit(log.stdout.strip())
        return
    result = subprocess.run(["uv", "tool", "upgrade", "pilot-agent"], check=False)
    raise typer.Exit(result.returncode)


@app.command("model")
def model_command(
    target: str | None = typer.Argument(None),
    list_only: bool = typer.Option(False, "--list"),
) -> None:
    cfg = load_config_or_exit()
    if list_only:
        render_model_table(cfg.provider)
        return
    if target is None:
        if _interactive():
            provider_name = _choose_model_provider(cfg)
            model_name = _choose_model(provider_name)
            update_config_values(
                _config_write_path(),
                {
                    "provider": provider_name,
                    "model": model_name,
                    "api_key_env": provider_key_env(provider_name),
                },
            )
            emit(f"✓ {provider_name}:{model_name}")
            return
        render_model_table(cfg.provider)
        emit("Switch with: pilot-agent model <provider>:<model>")
        return
    if ":" in target:
        provider_name, model_name = target.split(":", 1)
    else:
        provider_name, model_name = cfg.provider, target
    try:
        api_key_env = provider_key_env(provider_name)
    except ValueError as exc:
        emit(f"Error: {exc}. Run: pilot-agent setup")
        raise typer.Exit(1) from None
    update_config_values(
        _config_write_path(),
        {
            "provider": provider_name,
            "model": model_name,
            "api_key_env": api_key_env,
        },
    )
    emit(f"✓ {provider_name}:{model_name}")


def render_model_table(provider_name: str) -> None:
    api_key = get_credential(
        provider_name,
        default_home(),
        env_name=provider_key_env(provider_name),
    )
    table = simple_table("provider", "model", "context", "tools", "price/Mtok")
    for model in list_models(provider_name, api_key=api_key):
        price = "-"
        if model.input_price is not None and model.output_price is not None:
            price = f"${model.input_price:g}/${model.output_price:g}"
        table.add_row(
            model.provider,
            model.name,
            str(model.context_window),
            str(model.supports_tools).lower(),
            price,
        )
    emit(table)


def _choose_model_provider(cfg: PilotAgentConfig) -> str:
    prompt = PilotAgentInput(history_path=default_home() / "input_history")
    default = {name: idx for idx, name in enumerate(PROVIDERS, start=1)}.get(cfg.provider, 1)
    lines = []
    for idx, provider_name in enumerate(PROVIDERS, start=1):
        resolved = resolve_credential(
            provider_name,
            default_home(),
            env_name=provider_key_env(provider_name),
        )
        status = "✓" if resolved.value else "✗ no key"
        lines.append(f"{idx}. {provider_name} ({status})")
    choice = prompt.ask_int(
        "Choose provider: " + "  ".join(lines),
        default=default,
        choices=["1", "2", "3"],
    )
    return PROVIDERS[choice - 1]


def _choose_model(provider_name: str) -> str:
    prompt = PilotAgentInput(history_path=default_home() / "input_history")
    api_key = get_credential(
        provider_name,
        default_home(),
        env_name=provider_key_env(provider_name),
    )
    models = list_models(provider_name, api_key=api_key)
    choices = [str(idx) for idx in range(1, min(len(models), 20) + 1)]
    rendered = "  ".join(
        f"{idx}. {model.name}" for idx, model in enumerate(models[:20], start=1)
    )
    choice = prompt.ask_int(f"Choose model: {rendered}", default=1, choices=choices)
    return models[choice - 1].name


@app.command("backend")
def backend_command(target: str | None = typer.Argument(None)) -> None:
    cfg = load_config_or_exit()
    if target is None:
        table = simple_table("setting", "value", "source")
        value = _with_recommendation("backend", cfg.backend)
        table.add_row("backend", value, cfg.sources.get("backend", "defaults"))
        table.add_row(
            "sandbox.image",
            cfg.sandbox.image,
            cfg.sources.get("sandbox.image", "defaults"),
        )
        table.add_row(
            "sandbox.network",
            cfg.sandbox.network,
            cfg.sources.get("sandbox.network", "defaults"),
        )
        emit(table)
        emit("Switch with: pilot-agent backend docker|local")
        return
    if target not in {"docker", "local"}:
        emit("Error: backend must be docker or local")
        raise typer.Exit(1)
    update_config_values(_config_write_path(), {"backend": target})
    emit(f"✓ backend {target}")


@app.command("tools")
def tools_command(
    tool: str | None = typer.Argument(None),
    enable: bool = typer.Option(False, "--enable"),
    disable: bool = typer.Option(False, "--disable"),
    provider: str | None = typer.Option(None, "--provider"),
) -> None:
    cfg = load_config_or_exit()
    if tool is None:
        render_tools_table(cfg)
        emit("Change with: pilot-agent tools <web_search|web_fetch|deploy> --enable|--disable")
        return
    if tool not in {"web_search", "web_fetch", "deploy"}:
        emit("Error: unknown tool. Use web_search, web_fetch, or deploy")
        raise typer.Exit(1)
    if enable and disable:
        emit("Error: choose only one of --enable or --disable")
        raise typer.Exit(1)
    updates: dict[str, object] = {}
    if enable or disable:
        updates[f"tools.{tool}.enabled"] = enable
    if provider is not None:
        if tool != "web_search":
            emit("Error: --provider applies only to web_search")
            raise typer.Exit(1)
        updates["tools.web_search.provider"] = provider
    if updates:
        update_config_values(_config_write_path(), updates)
        cfg = load_config_or_exit()
    render_tools_table(cfg)


def render_tools_table(cfg: PilotAgentConfig) -> None:
    home = default_home()
    table = simple_table("tool", "state", "configuration")
    table.add_row("bash/file_ops/run_and_check/ask_user/skills", "✓ core", "always enabled")
    search_provider = cfg.tools.web_search.provider
    key = get_credential(search_provider, home)
    search_state = "✓ enabled" if cfg.tools.web_search.enabled and key else "⚠ needs key"
    if not cfg.tools.web_search.enabled:
        search_state = "✗ disabled"
    table.add_row(
        "web_search",
        search_state,
        _with_recommendation("tools.web_search.provider", search_provider),
    )
    table.add_row(
        "web_fetch",
        "✓ enabled" if cfg.tools.web_fetch.enabled else "✗ disabled",
        "SSRF checks",
    )
    vercel_key = get_credential("vercel", home, env_name=cfg.phases.deploy.vercel_token_env)
    deploy_state = (
        "✓ enabled" if cfg.tools.deploy.enabled or cfg.phases.deploy.enabled else "✗ disabled"
    )
    table.add_row(
        "deploy",
        deploy_state,
        "vercel token " + ("set" if vercel_key else "from env/ask later"),
    )
    emit(table)


@app.command("settings")
def settings() -> None:
    cfg = load_config_or_exit()
    home = default_home()
    table = simple_table("section", "setting", "value", "source")
    resolved = resolve_credential(cfg.provider, home, env_name=cfg.api_key_env)
    table.add_row(
        "provider",
        "model",
        f"{cfg.provider}:{cfg.model}",
        cfg.sources.get("model", "defaults"),
    )
    table.add_row("provider", "api key", mask_secret(resolved.value), resolved.source)
    table.add_row(
        "execution",
        "backend",
        _with_recommendation("backend", cfg.backend),
        cfg.sources.get("backend", "defaults"),
    )
    table.add_row(
        "execution",
        "sandbox",
        f"{cfg.sandbox.image} · network {cfg.sandbox.network}",
        "config",
    )
    search_key = get_credential(cfg.tools.web_search.provider, home)
    table.add_row(
        "tools",
        "web_search",
        f"{'✓' if cfg.tools.web_search.enabled else '✗'} {cfg.tools.web_search.provider} · "
        f"{'key set' if search_key else 'key missing'}",
        cfg.sources.get("tools.web_search.enabled", "defaults"),
    )
    table.add_row(
        "tools",
        "web_fetch",
        "✓ enabled" if cfg.tools.web_fetch.enabled else "✗ disabled",
        "config",
    )
    table.add_row(
        "tools",
        "deploy",
        "✓ enabled" if cfg.tools.deploy.enabled else "✗ disabled",
        "config",
    )
    lessons = _lesson_count(home)
    skills = build_skill_registry()
    learned = sum(1 for item in skills.records.values() if item.meta.source == "learned")
    table.add_row(
        "memory",
        "summary",
        f"lessons {lessons} · skills {len(skills.records)} ({learned} learned)",
        "home",
    )
    emit(table)
    emit(
        "Change: pilot-agent setup --reconfigure · pilot-agent tools · "
        "pilot-agent backend · pilot-agent auth set <name>"
    )


@app.command()
def status() -> None:
    root = Path(".").resolve()
    if not (root / ".pilot-agent").exists():
        emit("Project is not initialized. Run: pilot-agent init")
        raise typer.Exit(1)
    phase = restore_phase_from_session(root)
    todo_done, todo_total = _todo_progress(state_path(root))
    turns, token_total = _session_stats(session_path(root))
    table = simple_table("field", "value")
    table.add_row("phase", phase or "complete")
    table.add_row("todo", f"{todo_done}/{todo_total}")
    table.add_row("turns", str(turns))
    table.add_row("tokens", str(token_total))
    emit(table)


@app.command()
def run(
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
) -> None:
    _ensure_config_for_run()
    cfg = load_config_or_exit(provider=provider, model=model)
    resolve_key_or_exit(cfg)
    _ensure_project_for_run()
    _handle_reentry_for_completed_project()
    run_loop(cfg)


@app.command()
def resume(
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
) -> None:
    _ensure_config_for_run()
    cfg = load_config_or_exit(provider=provider, model=model)
    resolve_key_or_exit(cfg)
    _ensure_project_for_run(resume_mode=True)
    run_loop(cfg)


@config_app.callback(invoke_without_command=True)
def config_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        render_config(load_config_or_exit())


@config_app.command("get")
def config_get(key: str) -> None:
    try:
        typer.echo(str(config_value(load_config_or_exit(), key)))
    except KeyError:
        emit(f"Error: unknown config key {key!r}. Run: pilot-agent config")
        raise typer.Exit(1) from None


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    path = _config_write_path()
    try:
        set_config_value(path, key, value)
    except Exception as exc:
        emit(f"Error: invalid value for {key}: {exc}")
        raise typer.Exit(1) from None
    emit(f"set {key} in {path}")


@config_app.command("path")
def config_path_command() -> None:
    typer.echo(str(_config_write_path()))


@config_app.command("edit")
def config_edit() -> None:
    path = _config_write_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    editor = os.environ.get("EDITOR")
    if not editor:
        emit("Error: EDITOR is not set. Run: pilot-agent config path")
        raise typer.Exit(1) from None
    subprocess.run([editor, str(path)], check=False)


@auth_app.command("set")
def auth_set(service: str, value: str | None = typer.Argument(None)) -> None:
    home = default_home()
    secret = value
    if secret is None:
        secret = PilotAgentInput(history_path=home / "input_history").prompt(
            f"Key for {service} ({service_env_var(service)})",
            password=True,
            default="",
        )
    if not secret:
        emit(f"skipped {service}; no key stored")
        raise typer.Exit(1)
    if service in PROVIDERS:
        result = validate_provider_key(service, secret, timeout_s=5)
        if result.status == "fail":
            emit(f"Error: API rejected {service} key: {result.details}")
            raise typer.Exit(1)
        if result.status == "warn":
            emit(f"Warning: {result.details}")
    path = set_credential(service, secret, home)
    emit(f"✓ stored {service} credential in {path}")


@auth_app.command("status")
def auth_status() -> None:
    home = default_home()
    services = sorted({*PROVIDERS, "vercel", *credential_services(home)})
    table = simple_table("service", "source", "credential", "env")
    for service in services:
        env_name = service_env_var(service)
        resolved = resolve_credential(service, home, env_name=env_name)
        table.add_row(service, resolved.source, mask_secret(resolved.value), env_name)
    emit(table)
    ok, mode = credentials_permissions(home)
    if not ok:
        path = credentials_path(home)
        emit(f"Warning: {path} permissions are {mode}. Run: chmod 600 {path}")


@auth_app.command("remove")
def auth_remove(service: str) -> None:
    if remove_credential(service, default_home()):
        emit(f"✓ removed {service} from {credentials_path(default_home())}")
        return
    emit(f"{service} was not stored in {credentials_path(default_home())}")


@app.command("delete")
def delete_command(
    all_: bool = typer.Option(
        False,
        "--all",
        help="Remove Pilot Agent install files, user home, and current project state.",
    ),
    config: bool = typer.Option(False, "--config", help="Remove ~/.pilot-agent/config.yaml."),
    credentials: bool = typer.Option(
        False,
        "--credentials",
        help="Remove ~/.pilot-agent/credentials.yaml.",
    ),
    memory: bool = typer.Option(
        False,
        "--memory",
        help="Remove lessons, learned skills, and input history.",
    ),
    install: bool = typer.Option(
        False,
        "--install",
        help="Remove ~/.local/bin/pilot-agent and ~/.pilot-agent-src.",
    ),
    project: bool = typer.Option(
        False,
        "--project",
        help="Remove .pilot-agent from the current project.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation."),
) -> None:
    no_target = all([not all_, not config, not credentials, not memory, not install, not project])
    if no_target:
        emit(
            "Choose at least one target: --all, --config, --credentials, "
            "--memory, --install, or --project"
        )
        raise typer.Exit(1)
    targets = _delete_targets(
        all_=all_,
        config=config,
        credentials=credentials,
        memory=memory,
        install=install,
        project=project,
    )
    table = simple_table("target", "path", "state")
    for label, path in targets:
        table.add_row(label, str(path), "exists" if path.exists() else "missing")
    emit(table)
    emit("Docker images and volumes are not removed. Project code changes are not reverted.")
    if dry_run:
        return
    existing = [(label, path) for label, path in targets if path.exists()]
    if not existing:
        emit("nothing to delete")
        return
    if not yes:
        if not _interactive():
            emit("Refusing to delete without confirmation in non-interactive mode. Add --yes.")
            raise typer.Exit(1)
        if not typer.confirm("Delete these Pilot Agent files?", default=False):
            raise typer.Exit(1)
    for label, path in existing:
        _remove_known_path(path)
        emit(f"removed {label}: {path}")


def _delete_targets(
    *,
    all_: bool,
    config: bool,
    credentials: bool,
    memory: bool,
    install: bool,
    project: bool,
) -> list[tuple[str, Path]]:
    home = default_home()
    targets: list[tuple[str, Path]] = []
    if all_:
        install = True
        project = True
        targets.append(("home", home))
    else:
        if config:
            targets.append(("config", user_config_path(home)))
        if credentials:
            targets.append(("credentials", credentials_path(home)))
        if memory:
            targets.extend(
                [
                    ("lessons", home / "lessons.md"),
                    ("skills", home / "skills"),
                    ("input history", home / "input_history"),
                ]
            )
    if install:
        source = Path(os.environ.get("PILOT_AGENT_SRC", "~/.pilot-agent-src")).expanduser()
        bin_dir = Path(os.environ.get("PILOT_AGENT_BIN_DIR", "~/.local/bin")).expanduser()
        targets.extend(
            [
                ("wrapper", bin_dir / "pilot-agent"),
                ("source checkout", source),
            ]
        )
    if project:
        targets.append(("project state", Path(".").resolve() / ".pilot-agent"))
    return _dedupe_targets(targets)


def _dedupe_targets(targets: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    seen: set[Path] = set()
    unique: list[tuple[str, Path]] = []
    for label, path in targets:
        resolved = path.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append((label, path.expanduser()))
    return unique


def _remove_known_path(path: Path) -> None:
    resolved = path.expanduser().resolve(strict=False)
    forbidden = {Path.home().resolve(), Path("/")}
    if resolved in forbidden:
        raise RuntimeError(f"refusing to delete unsafe path: {resolved}")
    if not resolved.exists() and not resolved.is_symlink():
        return
    if resolved.is_dir() and not resolved.is_symlink():
        shutil.rmtree(resolved)
        return
    resolved.unlink()


@sandbox_app.command("build")
def sandbox_build(
    image: str = typer.Option("pilot-agent-sandbox:latest", "--image"),
) -> None:
    result = subprocess.run(
        ["docker", "build", "-f", "Dockerfile.sandbox", "-t", image, "."],
        text=True,
        check=False,
    )
    raise typer.Exit(result.returncode)


@sandbox_app.command("clean")
def sandbox_clean() -> None:
    listed = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "name=pilot-agent-sbx-",
            "--format",
            "{{.Names}}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    names = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not names:
        emit("no sandbox containers")
        return
    subprocess.run(["docker", "rm", "-f", *names], check=False)
    emit(f"removed {len(names)} sandbox containers")


@sandbox_app.command("expose")
def sandbox_expose(port: int) -> None:
    emit(
        "Manual port exposure requires recreating the session sandbox. "
        f"Use Docker directly for now: docker run -p {port}:{port} ..."
    )


@skills_app.command("list")
def skills_list() -> None:
    table = simple_table("name", "source", "success/failure", "deprecated")
    for record in sorted(build_skill_registry().records.values(), key=lambda item: item.meta.name):
        meta = record.meta
        table.add_row(
            meta.name,
            meta.source,
            f"{meta.success_count}/{meta.failure_count}",
            str(meta.deprecated).lower(),
        )
    emit(table)


@skills_app.command("show")
def skills_show(name: str) -> None:
    try:
        emit(build_skill_registry().load(name))
    except ValueError as exc:
        emit(f"Error: {exc}")
        raise typer.Exit(1) from None


@skills_app.command("new")
def skills_new() -> None:
    editor = os.environ.get("EDITOR")
    if not editor:
        emit("Error: EDITOR is not set. Run: pilot-agent skills list")
        raise typer.Exit(1)
    template = """---
name: new-skill
description: One-line description
triggers: []
version: 1
source: learned
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
## Steps
## Known pitfalls
## Verified commands
"""
    with tempfile.NamedTemporaryFile("w+", suffix=".md", encoding="utf-8", delete=False) as handle:
        handle.write(template)
        handle.flush()
        path = Path(handle.name)
    subprocess.run([editor, str(path)], check=False)
    content = path.read_text(encoding="utf-8")
    saved = build_skill_registry().save(content)
    emit(f"saved {saved}")


@lessons_app.callback(invoke_without_command=True)
def lessons_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    home = default_home()
    path = home / "lessons.md"
    emit(path.read_text(encoding="utf-8") if path.exists() else "")


@lessons_app.command("clear")
def lessons_clear(force: bool = typer.Option(False, "--yes", "-y")) -> None:
    if not force and not typer.confirm("Clear lessons.md?"):
        raise typer.Exit(1)
    home = default_home()
    path = home / "lessons.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    emit(f"cleared {path}")


@sessions_app.command("list")
def sessions_list() -> None:
    root = Path(".").resolve()
    table = simple_table("project", "phase", "turns", "status", "path")
    session = session_path(root)
    if session.exists():
        phase = restore_phase_from_session(root)
        turns, _ = _session_stats(session)
        status_text = "resume" if phase in PHASES else "complete"
        table.add_row(root.name, phase, str(turns), status_text, str(session))
    emit(table)


def _git_commit(cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _package_version() -> str:
    try:
        return metadata.version("pilot-agent")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _lesson_count(home: Path) -> int:
    path = home / "lessons.md"
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    )


def _config_write_path() -> Path:
    return GLOBAL_CONFIG_PATH or user_config_path()


def _with_recommendation(key: str, value: str) -> str:
    recommended = RECOMMENDED.get(key)
    if recommended is None or value == recommended["value"]:
        return f"{value} ✓"
    return f"{value} (recommended: {recommended['value']})"


def _todo_progress(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    in_todo = False
    done = 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_todo = line.strip().lower() == "## todo"
            continue
        if not in_todo:
            continue
        stripped = line.strip().lower()
        if stripped.startswith("- ["):
            total += 1
            if stripped.startswith("- [x]"):
                done += 1
    return done, total


def _session_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    turns = 0
    tokens = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("_type") == "Message":
            turns += 1
            raw_tokens = data.get("tokens")
            if isinstance(raw_tokens, int):
                tokens += raw_tokens
    return turns, tokens


if __name__ == "__main__":
    app()
