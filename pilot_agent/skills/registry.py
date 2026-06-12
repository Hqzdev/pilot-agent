from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SkillMeta(BaseModel):
    name: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    version: int = 1
    source: Literal["builtin", "learned"] = "learned"
    success_count: int = 0
    failure_count: int = 0
    deprecated: bool = False


@dataclass
class SkillRecord:
    meta: SkillMeta
    path: Path


class SkillRegistry:
    def __init__(self, paths: list[Path], home: Path | None = None):
        self.paths = paths
        self.home = home or Path(os.environ.get("PILOT_AGENT_HOME", "~/.pilot-agent")).expanduser()
        self.learned_dir = self.home / "skills"
        self.records: dict[str, SkillRecord] = {}
        self._scan()

    def _scan(self) -> None:
        self.records.clear()
        for directory in self.paths:
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.md")):
                meta = SkillMeta.model_validate(_read_frontmatter(path))
                self.records[meta.name] = SkillRecord(meta=meta, path=path)

    def index_for_prompt(self, phase: str, stack: list[str]) -> str:
        stack_set = {item.lower() for item in [*stack, phase]}
        lines = [
            "Available skills (call load_skill(name) BEFORE the matching task):",
        ]
        for record in sorted(self.records.values(), key=lambda item: item.meta.name):
            self._maybe_deprecate(record)
            meta = record.meta
            trigger_set = {item.lower() for item in meta.triggers}
            if meta.deprecated:
                continue
            if trigger_set and not trigger_set.intersection(stack_set):
                continue
            lines.append(f"- {meta.name}: {meta.description}")
        return "\n".join(lines)

    def load(self, name: str) -> str:
        try:
            return self.records[name].path.read_text(encoding="utf-8")
        except KeyError as exc:
            raise ValueError(f"unknown skill: {name}") from exc

    def save(self, content: str) -> Path:
        meta, body = _split_skill(content)
        self.learned_dir.mkdir(parents=True, exist_ok=True)
        existing = self.records.get(meta.name)
        if existing is not None:
            merged_body = _merge_known_pitfalls(existing.path.read_text(encoding="utf-8"), body)
            meta = existing.meta.model_copy(
                update={"version": existing.meta.version + 1, "source": "learned"}
            )
            content = _format_skill(meta, merged_body)
            path = existing.path
        else:
            meta = meta.model_copy(update={"source": "learned"})
            path = self.learned_dir / f"{_slug(meta.name)}.md"
            content = _format_skill(meta, body)
        path.write_text(content, encoding="utf-8")
        self.records[meta.name] = SkillRecord(meta=meta, path=path)
        return path

    def record_outcome(self, name: str, success: bool) -> None:
        record = self.records[name]
        update = {
            "success_count": record.meta.success_count + (1 if success else 0),
            "failure_count": record.meta.failure_count + (0 if success else 1),
        }
        record.meta = record.meta.model_copy(update=update)
        self._maybe_deprecate(record)
        content = record.path.read_text(encoding="utf-8")
        _, body = _split_skill(content)
        record.path.write_text(_format_skill(record.meta, body), encoding="utf-8")

    def _maybe_deprecate(self, record: SkillRecord) -> None:
        meta = record.meta
        total = meta.success_count + meta.failure_count
        if (
            meta.source == "learned"
            and total >= 3
            and meta.failure_count > meta.success_count
            and not meta.deprecated
        ):
            record.meta = meta.model_copy(update={"deprecated": True})
            content = record.path.read_text(encoding="utf-8")
            _, body = _split_skill(content)
            record.path.write_text(_format_skill(record.meta, body), encoding="utf-8")


def _read_frontmatter(path: Path) -> dict[str, object]:
    lines: list[str] = []
    with path.open(encoding="utf-8") as handle:
        if handle.readline().strip() != "---":
            raise ValueError(f"skill missing frontmatter: {path}")
        for line in handle:
            if line.strip() == "---":
                break
            lines.append(line)
    data = yaml.safe_load("".join(lines)) or {}
    if not isinstance(data, dict):
        raise ValueError(f"invalid frontmatter: {path}")
    return data


def _split_skill(content: str) -> tuple[SkillMeta, str]:
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, flags=re.S)
    if not match:
        raise ValueError("skill content must start with YAML frontmatter")
    raw_meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(raw_meta, dict):
        raise ValueError("skill frontmatter must be a mapping")
    return SkillMeta.model_validate(raw_meta), match.group(2)


def _format_skill(meta: SkillMeta, body: str) -> str:
    frontmatter = yaml.safe_dump(meta.model_dump(), sort_keys=False, allow_unicode=True)
    return f"---\n{frontmatter}---\n{body.lstrip()}"


def _section(text: str, heading: str) -> str:
    pattern = rf"(^## {re.escape(heading)}\n.*?)(?=^## |\Z)"
    match = re.search(pattern, text, flags=re.S | re.M)
    return match.group(1).strip() if match else f"## {heading}"


def _merge_known_pitfalls(existing_content: str, new_body: str) -> str:
    _, existing_body = _split_skill(existing_content)
    new_pitfalls = _section(new_body, "Known pitfalls")
    if new_pitfalls == "## Known pitfalls":
        return existing_body
    return existing_body.rstrip() + "\n\n" + new_pitfalls + "\n"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
