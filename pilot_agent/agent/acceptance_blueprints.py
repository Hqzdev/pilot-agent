from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptanceBlueprint:
    id: str
    title: str
    cadence: str
    purpose: str
    commands: tuple[str, ...]
    required_credentials: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


BLUEPRINTS: tuple[AcceptanceBlueprint, ...] = (
    AcceptanceBlueprint(
        id="nightly-checks",
        title="Nightly local acceptance",
        cadence="nightly after main changes",
        purpose="Re-run the repository quality bar and surface regressions before users hit them.",
        commands=(
            "UV_CACHE_DIR=.uv-cache uv sync --all-groups --frozen",
            "scripts/run_tests.sh",
            "pilot-agent doctor --json",
        ),
        artifacts=(
            "test transcript",
            "doctor JSON",
        ),
        notes=(
            "This blueprint validates the existing local MVP pipeline; it does not deploy.",
            "Treat a red doctor check as an acceptance failure unless explicitly waived.",
        ),
    ),
    AcceptanceBlueprint(
        id="dependency-audit",
        title="Dependency drift audit",
        cadence="weekly or before a release tag",
        purpose="Detect lockfile drift and dependency metadata issues without adding new services.",
        commands=(
            "uv lock --check",
            "UV_CACHE_DIR=.uv-cache uv sync --all-groups --frozen",
            "UV_CACHE_DIR=.uv-cache uv run python -m pip check",
        ),
        artifacts=(
            "uv lock check output",
            "pip check output",
        ),
        notes=(
            "Security scanners can be wired later; this v1 blueprint sticks to installed tooling.",
        ),
    ),
    AcceptanceBlueprint(
        id="deploy-verification",
        title="Deploy readiness verification",
        cadence="before release or deploy phase",
        purpose="Confirm local package and container build paths still work before handoff.",
        commands=(
            "UV_CACHE_DIR=.uv-cache uv build",
            "docker compose build",
            "pilot-agent doctor --json",
        ),
        required_credentials=(
            "VERCEL_TOKEN when deploy phase is enabled",
        ),
        artifacts=(
            "dist build output",
            "docker build output",
            "doctor JSON",
        ),
        notes=(
            "This is a readiness blueprint; publishing remains intentionally separate.",
        ),
    ),
)

_BY_ID = {blueprint.id: blueprint for blueprint in BLUEPRINTS}


def list_blueprints() -> tuple[AcceptanceBlueprint, ...]:
    return BLUEPRINTS


def get_blueprint(blueprint_id: str) -> AcceptanceBlueprint:
    try:
        return _BY_ID[blueprint_id]
    except KeyError as exc:
        known = ", ".join(sorted(_BY_ID))
        raise ValueError(f"unknown acceptance blueprint {blueprint_id!r}; known: {known}") from exc


def render_blueprint(blueprint: AcceptanceBlueprint) -> str:
    lines = [
        f"# {blueprint.title}",
        f"id: {blueprint.id}",
        f"cadence: {blueprint.cadence}",
        "",
        blueprint.purpose,
        "",
        "Commands:",
        *[f"- {command}" for command in blueprint.commands],
    ]
    if blueprint.required_credentials:
        lines.extend(
            [
                "",
                "Required credentials:",
                *[f"- {item}" for item in blueprint.required_credentials],
            ]
        )
    if blueprint.artifacts:
        lines.extend(["", "Artifacts:", *[f"- {item}" for item in blueprint.artifacts]])
    if blueprint.notes:
        lines.extend(["", "Notes:", *[f"- {item}" for item in blueprint.notes]])
    return "\n".join(lines)
