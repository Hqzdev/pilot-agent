"""Doctor checks for environment, config, provider, tools, memory, and project state."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pilot_agent.agent.state import session_path, state_path
from pilot_agent.backends import backend_from_config
from pilot_agent.cli.auth import STATIC_MODELS, validate_provider_key
from pilot_agent.config.credentials import (
    credentials_path,
    credentials_permissions,
    get_credential,
    resolve_credential,
)
from pilot_agent.config.schema import RECOMMENDED, PilotAgentConfig, default_home, load_config
from pilot_agent.providers.base import _PROVIDER_MODULES
from pilot_agent.skills.registry import SkillRegistry

CheckStatus = Literal["pass", "warn", "fail"]


@dataclass
class CheckResult:
    status: CheckStatus
    name: str
    details: str
    fix: str | None = None


def run_doctor_checks(
    *,
    project_root: Path | None = None,
    home: Path | None = None,
) -> list[CheckResult]:
    root = (project_root or Path(".")).resolve()
    agent_home = home or default_home()
    checks: list[CheckResult] = []
    checkers: list[Callable[[], CheckResult]] = [
        lambda: check_python(),
        lambda: check_platform(),
        lambda: check_home(agent_home),
        check_git,
        lambda: check_config(root, agent_home),
        lambda: check_provider_registered(root, agent_home),
        lambda: check_api_key(root, agent_home),
        lambda: check_credentials_file_permissions(agent_home),
        lambda: check_provider_live_api(root, agent_home),
        lambda: check_model(root, agent_home),
        lambda: check_context_window(root, agent_home),
        lambda: check_backend(root, agent_home),
        lambda: check_recommendations(root, agent_home),
        check_node,
        check_npm,
        check_vercel_cli,
        lambda: check_vercel_token(root, agent_home),
        lambda: check_optional_tools(root, agent_home),
        lambda: check_lessons(agent_home),
        lambda: check_skills(agent_home),
        lambda: check_project(root),
    ]
    for checker in checkers:
        try:
            checks.append(checker())
        except Exception as exc:
            checks.append(CheckResult("fail", "doctor internal check", str(exc)))
    return checks


def checks_to_json(checks: list[CheckResult]) -> str:
    return json.dumps([asdict(check) for check in checks], ensure_ascii=False, indent=2)


def has_failures(checks: list[CheckResult]) -> bool:
    return any(check.status == "fail" for check in checks)


def check_python() -> CheckResult:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= (3, 12):  # noqa: UP036 - doctor reports runtime state.
        return CheckResult("pass", "Python >= 3.12", version)
    return CheckResult(
        "fail",
        "Python >= 3.12",
        version,
        "Install Python 3.12+ or use Docker",
    )


def check_platform() -> CheckResult:
    system = platform.system()
    if system in {"Darwin", "Linux"}:
        return CheckResult("pass", "supported platform", platform.platform())
    return CheckResult("fail", "supported platform", system, "Use WSL2 on Windows")


def check_home(home: Path) -> CheckResult:
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult("pass", "~/.pilot-agent writable", str(home))
    except OSError as exc:
        return CheckResult(
            "fail",
            "~/.pilot-agent writable",
            str(exc),
            "Run: mkdir -p ~/.pilot-agent",
        )


def check_git() -> CheckResult:
    path = shutil.which("git")
    if path:
        return CheckResult("pass", "git available", path)
    return CheckResult("fail", "git available", "not found", "Install git")


def check_config(project_root: Path, home: Path) -> CheckResult:
    try:
        cfg = load_config(home=home, project_root=project_root)
    except Exception as exc:
        return CheckResult(
            "fail",
            "config.yaml valid",
            str(exc),
            "Run: pilot-agent setup --reconfigure",
        )
    return CheckResult("pass", "config.yaml valid", f"{cfg.provider}:{cfg.model}")


def _safe_config(project_root: Path, home: Path) -> PilotAgentConfig | None:
    try:
        return load_config(home=home, project_root=project_root)
    except Exception:
        return None


def check_provider_registered(project_root: Path, home: Path) -> CheckResult:
    try:
        cfg = load_config(home=home, project_root=project_root)
    except Exception as exc:
        return CheckResult("fail", "provider registered", str(exc), "Run: pilot-agent setup")
    if cfg.provider in _PROVIDER_MODULES:
        return CheckResult("pass", "provider registered", cfg.provider)
    known = ", ".join(sorted(_PROVIDER_MODULES))
    return CheckResult(
        "fail",
        "provider registered",
        f"{cfg.provider!r} not in {known}",
        "Run: pilot-agent setup --reconfigure",
    )


def check_api_key(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult("fail", "provider API key", "config invalid", "Run: pilot-agent setup")
    resolved = resolve_credential(cfg.provider, home, env_name=cfg.api_key_env)
    if not resolved.value:
        return CheckResult(
            "fail",
            "provider API key",
            f"not found for {cfg.provider}",
            f"Run: pilot-agent auth set {cfg.provider}",
        )
    return CheckResult("pass", "provider API key", f"{resolved.source} ({resolved.env_name})")


def check_credentials_file_permissions(home: Path) -> CheckResult:
    ok, mode = credentials_permissions(home)
    if ok:
        details = "not created yet" if mode is None else f"mode {mode}"
        return CheckResult("pass", "credentials.yaml permissions", details)
    path = credentials_path(home)
    return CheckResult(
        "warn",
        "credentials.yaml permissions",
        f"mode {mode}; expected 0o600",
        f"Run: chmod 600 {path}",
    )


def check_provider_live_api(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult("fail", "provider live API", "config invalid", "Run: pilot-agent setup")
    resolved = resolve_credential(cfg.provider, home, env_name=cfg.api_key_env)
    if not resolved.value:
        return CheckResult(
            "warn",
            "provider live API",
            "skipped; provider key missing",
            f"Run: pilot-agent auth set {cfg.provider}",
        )
    result = validate_provider_key(
        cfg.provider,
        resolved.value,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout_s=5,
    )
    latency = f" ({result.latency_ms}ms)" if result.latency_ms is not None else ""
    if result.status == "pass":
        return CheckResult("pass", "provider live API", result.details + latency)
    if result.status == "fail":
        return CheckResult(
            "fail",
            "provider live API",
            result.details + latency,
            f"Run: pilot-agent auth set {cfg.provider}",
        )
    return CheckResult("warn", "provider live API", result.details + latency)


def check_model(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult("fail", "model exists", "config invalid", "Run: pilot-agent setup")
    names = {model.name for model in STATIC_MODELS.get(cfg.provider, [])}
    if cfg.model in names:
        return CheckResult("pass", "model exists", cfg.model)
    return CheckResult("warn", "model exists", f"{cfg.model} not in local catalog")


def check_context_window(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult(
            "fail",
            "context_window known",
            "config invalid",
            "Run: pilot-agent setup",
        )
    for item in STATIC_MODELS.get(cfg.provider, []):
        if item.name == cfg.model:
            return CheckResult("pass", "context_window known", str(item.context_window))
    return CheckResult(
        "warn",
        "context_window known",
        f"{cfg.model} unknown; provider default will be used",
    )


def check_backend(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult("fail", "backend", "config invalid", "Run: pilot-agent setup")
    backend = backend_from_config(cfg, project_root)
    result = backend.healthcheck()
    backend.cleanup()
    return CheckResult(result.status, result.name, result.details, result.fix)


def check_recommendations(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult(
            "fail",
            "recommended settings",
            "config invalid",
            "Run: pilot-agent setup",
        )
    deviations: list[str] = []
    backend_rec = RECOMMENDED["backend"]["value"]
    if cfg.backend != backend_rec:
        deviations.append(f"backend={cfg.backend} (recommended: {backend_rec})")
    search_rec = RECOMMENDED["tools.web_search.provider"]["value"]
    if cfg.tools.web_search.provider != search_rec:
        deviations.append(f"web_search={cfg.tools.web_search.provider} (recommended: {search_rec})")
    if deviations:
        return CheckResult("warn", "recommended settings", "; ".join(deviations))
    return CheckResult("pass", "recommended settings", "using recommended defaults")


def check_node() -> CheckResult:
    path = shutil.which("node")
    if path:
        return CheckResult("pass", "node available", path)
    return CheckResult("fail", "node available", "not found", "Install node or use Docker")


def check_npm() -> CheckResult:
    path = shutil.which("npm")
    if path:
        return CheckResult("pass", "npm available", path)
    return CheckResult("fail", "npm available", "not found", "Install npm or use Docker")


def check_vercel_cli() -> CheckResult:
    path = shutil.which("vercel")
    if path:
        return CheckResult("pass", "vercel CLI available", path)
    return CheckResult("fail", "vercel CLI available", "not found", "Run: npm i -g vercel")


def check_vercel_token(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    env_name = "VERCEL_TOKEN"
    if cfg is not None:
        env_name = cfg.phases.deploy.vercel_token_env
    if env_name in os.environ:
        return CheckResult("pass", "VERCEL_TOKEN set", f"found ${env_name}")
    if get_credential("vercel", home, env_name=env_name):
        return CheckResult("pass", "VERCEL_TOKEN set", "credentials")
    return CheckResult(
        "warn",
        "VERCEL_TOKEN set",
        f"${env_name} not set",
        "Run: pilot-agent auth set vercel",
    )


def check_optional_tools(project_root: Path, home: Path) -> CheckResult:
    cfg = _safe_config(project_root, home)
    if cfg is None:
        return CheckResult("fail", "optional tools", "config invalid", "Run: pilot-agent setup")
    warnings: list[str] = []
    if (
        cfg.tools.web_search.enabled
        and cfg.tools.web_search.provider != "searxng"
        and not get_credential(cfg.tools.web_search.provider, home)
    ):
        warnings.append(f"{cfg.tools.web_search.provider} key missing")
    if cfg.tools.web_fetch.enabled:
        warnings.append("web_fetch enabled; SSRF checks active")
    if warnings:
        return CheckResult("warn", "optional tools", "; ".join(warnings), "Run: pilot-agent tools")
    return CheckResult("pass", "optional tools", "configured")


def check_lessons(home: Path) -> CheckResult:
    path = home / "lessons.md"
    if not path.exists():
        return CheckResult("pass", "lessons.md parses", "not created yet")
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return CheckResult("warn", "lessons.md parses", str(exc))
    return CheckResult("pass", "lessons.md parses", str(path))


def check_skills(home: Path) -> CheckResult:
    builtin = Path(__file__).parents[1] / "skills" / "builtin"
    try:
        registry = SkillRegistry([builtin, home / "skills"], home=home)
    except Exception as exc:
        return CheckResult("fail", "skills validate", str(exc))
    deprecated = sum(1 for item in registry.records.values() if item.meta.deprecated)
    status: CheckStatus = "warn" if deprecated else "pass"
    details = f"{len(registry.records)} skills, deprecated={deprecated}"
    return CheckResult(status, "skills validate", details)


def check_project(project_root: Path) -> CheckResult:
    if not (project_root / ".pilot-agent").exists():
        return CheckResult(
            "warn",
            "project initialized",
            "no .pilot-agent in cwd",
            "Run: pilot-agent init",
        )
    state = state_path(project_root)
    if not state.exists():
        return CheckResult("fail", "STATE.md exists", "missing", "Run: pilot-agent init")
    session = session_path(project_root)
    if session.exists():
        try:
            for line in session.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    json.loads(line)
        except json.JSONDecodeError as exc:
            return CheckResult(
                "fail",
                "session.jsonl readable",
                str(exc),
                "Move broken session.jsonl aside",
            )
    words = len(state.read_text(encoding="utf-8").split())
    if words > 4_000:
        return CheckResult("warn", "STATE.md size", f"{words} words; compact it")
    return CheckResult("pass", "project initialized", str(project_root / ".pilot-agent"))
