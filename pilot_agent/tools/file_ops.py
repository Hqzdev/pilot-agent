from __future__ import annotations

from pathlib import Path
from typing import Any

from pilot_agent.config.schema import default_home
from pilot_agent.tools.base import Tool

IGNORED = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".next"}


class ProjectPaths:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.home_memory = default_home().resolve()

    def resolve(self, path: str, *, write: bool = False) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        resolved = candidate.resolve()
        if self._inside(resolved, self.project_root):
            return resolved
        if not write and self._inside(resolved, self.home_memory):
            return resolved
        raise ValueError(f"path is outside project root: {path}")

    @staticmethod
    def _inside(path: Path, parent: Path) -> bool:
        return path == parent or parent in path.parents


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a file with line numbers for precise edit references."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "minimum": 1, "default": 1},
            "limit": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self, project_root: Path):
        self.paths = ProjectPaths(project_root)

    def execute(self, **kwargs: Any) -> str:
        path = str(kwargs["path"])
        offset = int(kwargs.get("offset", 1))
        limit = kwargs.get("limit")
        typed_limit = int(limit) if limit is not None else None
        resolved = self.paths.resolve(path)
        lines = resolved.read_text(encoding="utf-8").splitlines()
        start = max(offset - 1, 0)
        selected = lines[start : start + typed_limit if typed_limit is not None else None]
        return "\n".join(f"{idx:>4}\u2192{line}" for idx, line in enumerate(selected, start + 1))


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create parent directories and overwrite a file inside the project root."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def __init__(self, project_root: Path):
        self.paths = ProjectPaths(project_root)

    def execute(self, **kwargs: Any) -> str:
        path = str(kwargs["path"])
        content = str(kwargs["content"])
        resolved = self.paths.resolve(path, write=True)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"written {len(content.encode('utf-8'))} bytes to {path}"


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace a unique string in a project file; fails unless old_str occurs once."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_str": {"type": "string"},
            "new_str": {"type": "string"},
        },
        "required": ["path", "old_str", "new_str"],
        "additionalProperties": False,
    }

    def __init__(self, project_root: Path):
        self.paths = ProjectPaths(project_root)

    def execute(self, **kwargs: Any) -> str:
        path = str(kwargs["path"])
        old_str = str(kwargs["old_str"])
        new_str = str(kwargs["new_str"])
        resolved = self.paths.resolve(path, write=True)
        content = resolved.read_text(encoding="utf-8")
        count = content.count(old_str)
        if count != 1:
            raise ValueError(f"old_str must occur exactly once; found {count}")
        resolved.write_text(content.replace(old_str, new_str), encoding="utf-8")
        return f"edited {path}"


class ListFilesTool(Tool):
    name = "list_files"
    description = "List a project tree up to depth 3, ignoring common generated directories."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"path": {"type": "string", "default": "."}},
        "additionalProperties": False,
    }

    def __init__(self, project_root: Path):
        self.paths = ProjectPaths(project_root)
        self.project_root = project_root.resolve()

    def execute(self, **kwargs: Any) -> str:
        path = str(kwargs.get("path", "."))
        root = self.paths.resolve(path)
        output: list[str] = []
        self._walk(root, output, depth=0)
        return "\n".join(output)

    def _walk(self, path: Path, output: list[str], depth: int) -> None:
        if depth > 3 or path.name in IGNORED:
            return
        if path.name == "artifacts" and path.parent.name == ".pilot-agent":
            return
        rel = path.relative_to(self.project_root) if path != self.project_root else Path(".")
        prefix = "  " * depth
        output.append(f"{prefix}{rel.name}/" if path.is_dir() else f"{prefix}{rel.name}")
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name)):
                self._walk(child, output, depth + 1)
