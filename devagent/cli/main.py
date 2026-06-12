"""Typer CLI entry point for DevAgent commands and first-run preflight."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Callable
from importlib import metadata
from operator import methodcaller
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from devagent.agent.context import ContextManager
from devagent.agent.loop import AgentLoop, restore_phase_from_session
from devagent.agent.phases import PHASES
from devagent.agent.state import init_project_state, read_session_messages, session_path, state_path
from devagent.cli.auth import list_models, provider_key_env
from devagent.cli.doctor import checks_to_json, has_failures, run_doctor_checks
from devagent.cli.setup_wizard import run_setup_wizard
from devagent.config.schema import (
    DevAgentConfig,
    config_value,
    default_home,
    flatten_config,
    load_config,
    set_config_value,
    update_config_values,
    user_config_path,
)
from devagent.providers import Provider, from_config
from devagent.skills.registry import SkillRegistry
from devagent.tools.ask_user import AskUserTool
from devagent.tools.base import ToolRegistry
from devagent.tools.bash import BashTool
from devagent.tools.file_ops import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from devagent.tools.phase_tools import CompletePhaseTool
from devagent.tools.run_check import RunAndCheckTool
from devagent.tools.skill_tools import LoadSkillTool, SaveSkillTool

app = typer.Typer(help="DevAgent local MVP agent.")
skills_app = typer.Typer(help="Manage skills.")
config_app = typer.Typer(help="Manage configuration.")
lessons_app = typer.Typer(help="Manage lessons.")
sessions_app = typer.Typer(help="Manage sessions.")
app.add_typer(skills_app, name="skills")
app.add_typer(config_app, name="config")
app.add_typer(lessons_app, name="lessons")
app.add_typer(sessions_app, name="sessions")
console = Console()
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
        os.environ["DEVAGENT_VERBOSE"] = "1"
    if no_color:
        os.environ["NO_COLOR"] = "1"


def load_config_or_exit(provider: str | None = None, model: str | None = None) -> DevAgentConfig:
    try:
        return load_config(
            provider=provider or GLOBAL_PROVIDER,
            model=model or GLOBAL_MODEL,
            config_path=GLOBAL_CONFIG_PATH,
        )
    except Exception as exc:
        emit(f"Error: invalid config: {exc}")
        raise typer.Exit(1) from None


def resolve_key_or_exit(cfg: DevAgentConfig) -> None:
    try:
        cfg.resolve_key()
    except RuntimeError as exc:
        emit(f"Error: {exc}")
        raise typer.Exit(1) from None


def render_config(cfg: DevAgentConfig) -> None:
    table = Table("key", "value", "source")
    flat = flatten_config(cfg)
    for key in sorted(flat):
        value = flat[key]
        display = json.dumps(value) if isinstance(value, bool | int | float) else str(value)
        table.add_row(key, display, cfg.sources.get(key, "defaults"))
    table.add_row("api_key_present", str(bool(os.environ.get(cfg.api_key_env))).lower(), "env")
    emit(table)


def build_skill_registry() -> SkillRegistry:
    home = default_home()
    builtin = Path(__file__).parents[1] / "skills" / "builtin"
    return SkillRegistry([builtin, home / "skills"], home=home)


def build_tool_registry(project_root: Path, skills: SkillRegistry, timeout_s: int) -> ToolRegistry:
    tools = [
        AskUserTool(),
        BashTool(project_root),
        ReadFileTool(project_root),
        WriteFileTool(project_root),
        EditFileTool(project_root),
        ListFilesTool(project_root),
        RunAndCheckTool(project_root),
        LoadSkillTool(skills),
        SaveSkillTool(skills),
        CompletePhaseTool(),
    ]
    for tool in tools:
        tool.timeout_s = timeout_s
    return ToolRegistry(tools, project_root)


def run_loop(cfg: DevAgentConfig) -> None:
    project_root = Path(".").resolve()
    init_project_state(project_root)
    skills = build_skill_registry()
    provider = from_config(cfg)
    registry = build_tool_registry(project_root, skills, cfg.tool_timeout_s)
    session_log = project_root / ".devagent" / "session.jsonl"
    phase_name = restore_phase_from_session(project_root)
    history = read_session_messages(project_root)
    loop = AgentLoop(
        project_root=project_root,
        provider=provider,
        registry=registry,
        ctx=ContextManager(provider, cfg.budget_ratio, session_log=session_log),
        skills=skills,
        phase_name=phase_name,
        history=history,
        model_switcher=_make_model_switcher(cfg),
    )
    loop.run(max_turns=cfg.max_turns)


def _make_model_switcher(cfg: DevAgentConfig) -> Callable[[str], Provider]:
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
    if Confirm.ask("Конфиг не найден. Запустить devagent setup?", default=True):
        run_setup_wizard(config_path=GLOBAL_CONFIG_PATH)
        return
    emit("Run: devagent setup")
    raise typer.Exit(1)


def _ensure_project_for_run(*, resume_mode: bool = False) -> None:
    root = Path(".").resolve()
    if not (root / ".devagent").exists():
        if _interactive() and Confirm.ask(
            f"Проект не инициализирован. Запустить devagent init здесь ({root})?",
            default=True,
        ):
            init_project_state(root)
        else:
            emit("Project is not initialized. Run: devagent init")
            raise typer.Exit(1)
    if resume_mode:
        return
    session = session_path(root)
    if not _interactive() or not session.exists() or session.stat().st_size == 0:
        return
    phase = restore_phase_from_session(root)
    choice = Prompt.ask(
        f"Найдена незавершённая сессия (фаза {phase}). [R]esume / [N]ew / [A]bort?",
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
        table = Table("status", "check", "details", "fix")
        symbols = {"pass": "✓", "warn": "⚠", "fail": "✗"}
        for check in checks:
            table.add_row(symbols[check.status], check.name, check.details, check.fix or "")
        emit(table)
        if has_failures(checks):
            emit("Исправь ✗ и перезапусти devagent doctor")
    if has_failures(checks):
        raise typer.Exit(1)


@app.command()
def version() -> None:
    try:
        package_version = metadata.version("devagent")
    except metadata.PackageNotFoundError:
        package_version = "0.1.0"
    commit = _git_commit()
    emit(
        f"devagent {package_version}\n"
        f"commit {commit}\n"
        f"python {sys.version.split()[0]}\n"
        f"platform {platform.platform()}"
    )


@app.command()
def update() -> None:
    source = Path.home() / ".devagent-src"
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
    result = subprocess.run(["uv", "tool", "upgrade", "devagent"], check=False)
    raise typer.Exit(result.returncode)


@app.command("model")
def model_command(
    target: str | None = typer.Argument(None),
    list_only: bool = typer.Option(False, "--list"),
) -> None:
    cfg = load_config_or_exit()
    if list_only or target is None:
        render_model_table(cfg.provider)
        if target is None and not list_only:
            emit("Switch with: devagent model <provider>:<model>")
        return
    if ":" in target:
        provider_name, model_name = target.split(":", 1)
    else:
        provider_name, model_name = cfg.provider, target
    try:
        api_key_env = provider_key_env(provider_name)
    except ValueError as exc:
        emit(f"Error: {exc}. Run: devagent setup")
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
    api_key = os.environ.get(provider_key_env(provider_name))
    table = Table("provider", "model", "context", "tools")
    for model in list_models(provider_name, api_key=api_key):
        table.add_row(
            model.provider,
            model.name,
            str(model.context_window),
            str(model.supports_tools).lower(),
        )
    emit(table)


@app.command()
def status() -> None:
    root = Path(".").resolve()
    if not (root / ".devagent").exists():
        emit("Project is not initialized. Run: devagent init")
        raise typer.Exit(1)
    phase = restore_phase_from_session(root)
    todo_done, todo_total = _todo_progress(state_path(root))
    turns, token_total = _session_stats(session_path(root))
    table = Table("field", "value")
    table.add_row("phase", phase)
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
        emit(f"Error: unknown config key {key!r}. Run: devagent config")
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
        emit("Error: EDITOR is not set. Run: devagent config path")
        raise typer.Exit(1) from None
    subprocess.run([editor, str(path)], check=False)


@skills_app.command("list")
def skills_list() -> None:
    table = Table("name", "source", "success/failure", "deprecated")
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
        emit("Error: EDITOR is not set. Run: devagent skills list")
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
    home = Path(os.environ.get("DEVAGENT_HOME", "~/.devagent")).expanduser()
    path = home / "lessons.md"
    emit(path.read_text(encoding="utf-8") if path.exists() else "")


@lessons_app.command("clear")
def lessons_clear(force: bool = typer.Option(False, "--yes", "-y")) -> None:
    if not force and not typer.confirm("Очистить lessons.md?"):
        raise typer.Exit(1)
    home = Path(os.environ.get("DEVAGENT_HOME", "~/.devagent")).expanduser()
    path = home / "lessons.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    emit(f"cleared {path}")


@sessions_app.command("list")
def sessions_list() -> None:
    root = Path(".").resolve()
    table = Table("project", "phase", "turns", "status", "path")
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


def _config_write_path() -> Path:
    return GLOBAL_CONFIG_PATH or user_config_path()


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
