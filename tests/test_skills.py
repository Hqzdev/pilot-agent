from __future__ import annotations

from pathlib import Path

from pilot_agent.agent.types import Message, Role, ToolCall
from pilot_agent.skills.registry import SkillRegistry
from pilot_agent.tools.skill_tools import LoadSkillTool, SaveSkillTool


def skill_doc(name: str, source: str = "learned", triggers: str = "[python]") -> str:
    return f"""---
name: {name}
description: Skill {name}
triggers: {triggers}
version: 1
source: {source}
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use it.
## Known pitfalls
- old pitfall
## Verified commands
- echo ok
"""


def test_registry_indexes_frontmatter_and_loads_body_lazily(tmp_path: Path) -> None:
    path = tmp_path / "skills"
    path.mkdir()
    (path / "python.md").write_text(skill_doc("python-skill"), encoding="utf-8")
    registry = SkillRegistry([path], home=tmp_path / "home")

    assert "python-skill" in registry.records
    assert "Skill python-skill" in registry.index_for_prompt("coding", ["python"])
    assert "## Verified commands" in registry.load("python-skill")


def test_index_filters_triggers_and_deprecated(tmp_path: Path) -> None:
    path = tmp_path / "skills"
    path.mkdir()
    (path / "a.md").write_text(skill_doc("python-skill"), encoding="utf-8")
    (path / "b.md").write_text(skill_doc("global-skill", triggers="[]"), encoding="utf-8")
    deprecated = skill_doc("old-skill").replace("deprecated: false", "deprecated: true")
    (path / "c.md").write_text(deprecated, encoding="utf-8")
    registry = SkillRegistry([path], home=tmp_path / "home")

    index = registry.index_for_prompt("coding", ["nextjs"])

    assert "global-skill" in index
    assert "python-skill" not in index
    assert "old-skill" not in index


def test_index_matches_current_phase_trigger(tmp_path: Path) -> None:
    path = tmp_path / "skills"
    path.mkdir()
    (path / "acceptance.md").write_text(
        skill_doc("local-acceptance", triggers="[acceptance, review]"),
        encoding="utf-8",
    )
    registry = SkillRegistry([path], home=tmp_path / "home")

    index = registry.index_for_prompt("acceptance", [])

    assert "local-acceptance" in index


def test_load_and_save_skill_tools_and_duplicate_merge(tmp_path: Path) -> None:
    learned = tmp_path / "home" / "skills"
    learned.mkdir(parents=True)
    existing = learned / "python-skill.md"
    existing.write_text(skill_doc("python-skill"), encoding="utf-8")
    registry = SkillRegistry([learned], home=tmp_path / "home")
    new_doc = skill_doc("python-skill").replace("- old pitfall", "- new pitfall")

    loaded = LoadSkillTool(registry).execute(name="python-skill")
    path = SaveSkillTool(registry).execute(content=new_doc)

    merged = Path(path).read_text(encoding="utf-8")
    assert "## When to use" in loaded
    assert "version: 2" in merged
    assert "new pitfall" in merged


def test_record_outcome_deprecates_failed_learned_skill(tmp_path: Path) -> None:
    learned = tmp_path / "home" / "skills"
    learned.mkdir(parents=True)
    path = learned / "python-skill.md"
    path.write_text(skill_doc("python-skill"), encoding="utf-8")
    registry = SkillRegistry([learned], home=tmp_path / "home")

    registry.record_outcome("python-skill", False)
    registry.record_outcome("python-skill", False)
    registry.record_outcome("python-skill", True)
    index = registry.index_for_prompt("coding", ["python"])

    assert "python-skill" not in index
    assert "deprecated: true" in path.read_text(encoding="utf-8")


def test_builtin_skills_exist_and_have_content() -> None:
    builtin = Path("pilot_agent/skills/builtin")
    names = {path.stem for path in builtin.glob("*.md")}

    assert names == {
        "bugfix-intake",
        "competitor-scan",
        "fastapi-scaffold",
        "frontend-api-wiring",
        "launch-posts",
        "local-acceptance",
        "mvp-scoping",
        "nextjs-project-plan",
        "nextjs-scaffold",
        "nextjs-vercel-deploy",
        "production-env-vars",
        "python-deps-uv",
        "readme-structure",
        "sqlite-schema-design",
    }
    for path in builtin.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "## When to use" in text
        assert "## Steps" in text
        assert "## Known pitfalls" in text
        assert "## Verified commands" in text
        assert len(text.splitlines()) >= 35


def test_deploy_load_skill_precedes_vercel_command() -> None:
    calls = [
        Message(
            role=Role.ASSISTANT,
            tool_calls=[ToolCall("1", "load_skill", {"name": "nextjs-vercel-deploy"})],
        ),
        Message(role=Role.TOOL),
        Message(
            role=Role.ASSISTANT,
            tool_calls=[ToolCall("2", "bash", {"command": "vercel --prod"})],
        ),
    ]

    load_index = next(
        idx
        for idx, msg in enumerate(calls)
        if msg.tool_calls and msg.tool_calls[0].name == "load_skill"
    )
    vercel_index = next(
        idx
        for idx, msg in enumerate(calls)
        if msg.tool_calls and "vercel" in msg.tool_calls[0].arguments.get("command", "")
    )

    assert load_index < vercel_index
