from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_PLACEHOLDER = "[REDACTED]"

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9_-])("
    r"sk-[A-Za-z0-9_-]{10,}|"
    r"ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|"
    r"gh[ousr]_[A-Za-z0-9]{10,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[A-Za-z0-9_-]{30,}|"
    r"hf_[A-Za-z0-9]{10,}|"
    r"pypi-[A-Za-z0-9_-]{10,}|"
    r"npm_[A-Za-z0-9]{10,}|"
    r"gsk_[A-Za-z0-9]{10,}|"
    r"xai-[A-Za-z0-9]{20,}|"
    r"AKIA[A-Z0-9]{16}"
    r")(?![A-Za-z0-9_-])"
)
_ENV_ASSIGN_RE = re.compile(
    r"\b([A-Z0-9_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)[A-Z0-9_]*)"
    r"\s*=\s*(['\"]?)([^'\"\s]+)\2",
    re.IGNORECASE,
)
_JSON_FIELD_RE = re.compile(
    r'("(?:api_?key|token|secret|password|access_token|refresh_token|authorization|bearer|private_key)")'
    r'\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)
_AUTH_RE = re.compile(r"(Authorization:\s*(?:Bearer|Basic)\s+)(\S+)", re.IGNORECASE)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----"
)
_DB_URL_RE = re.compile(
    r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s/@]+:)([^@\s]+)(@)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"\b(https?|wss?|ftp)://[^\s'\"<>]+")
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "api_key",
    "apikey",
    "client_secret",
    "password",
    "auth",
    "jwt",
    "session",
    "secret",
    "key",
    "code",
    "signature",
    "x-amz-signature",
}

BLOCKED_PROJECT_ENV_BASENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.staging",
    ".envrc",
}
BLOCKED_HOME_FILES = {
    ".netrc",
    ".pgpass",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
}
BLOCKED_HOME_DIRS = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".kube",
    ".docker",
    ".azure",
}
BLOCKED_PILOT_HOME_FILES = {"credentials.yaml", ".env"}


def sanitize_text(value: str) -> str:
    """Make text safe for JSON/provider transport without changing normal prose."""

    if not value:
        return value
    value = _SURROGATE_RE.sub("\ufffd", value)
    return _CONTROL_RE.sub("\ufffd", value)


def sanitize_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list | tuple | set):
        return [sanitize_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_text(str(key)): sanitize_jsonable(item) for key, item in value.items()}
    return sanitize_text(str(value))


def mask_secret(value: str, *, head: int = 6, tail: int = 4) -> str:
    if len(value) <= head + tail + 4:
        return SECRET_PLACEHOLDER
    return f"{value[:head]}…{value[-tail:]}"


def redact_sensitive_text(text: str) -> str:
    """Redact common credentials before writing logs, artifacts, or session history."""

    if not text:
        return text
    text = sanitize_text(text)
    text = _PRIVATE_KEY_RE.sub(SECRET_PLACEHOLDER, text)
    text = _PREFIX_RE.sub(lambda m: mask_secret(m.group(1)), text)
    text = _AUTH_RE.sub(lambda m: m.group(1) + SECRET_PLACEHOLDER, text)
    text = _DB_URL_RE.sub(lambda m: m.group(1) + SECRET_PLACEHOLDER + m.group(3), text)
    text = _JSON_FIELD_RE.sub(lambda m: f'{m.group(1)}: "{SECRET_PLACEHOLDER}"', text)
    text = _ENV_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={SECRET_PLACEHOLDER}", text)
    return _URL_RE.sub(_redact_url, text)


def redact_jsonable(value: Any) -> Any:
    raw = json.dumps(sanitize_jsonable(value), ensure_ascii=False, default=str)
    return json.loads(redact_sensitive_text(raw))


def _redact_url(match: re.Match[str]) -> str:
    raw = match.group(0)
    try:
        parts = urlsplit(raw)
        query = parse_qsl(parts.query, keep_blank_values=True)
    except Exception:
        return raw
    if not query:
        return raw
    changed = False
    redacted: list[tuple[str, str]] = []
    for key, value in query:
        if key.lower() in _SENSITIVE_QUERY_KEYS:
            redacted.append((key, SECRET_PLACEHOLDER))
            changed = True
        else:
            redacted.append((key, value))
    if not changed:
        return raw
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted), parts.fragment))


def read_denial(path: Path, *, project_root: Path, pilot_home: Path) -> str | None:
    return _access_denial(path, project_root=project_root, pilot_home=pilot_home, write=False)


def write_denial(path: Path, *, project_root: Path, pilot_home: Path) -> str | None:
    return _access_denial(path, project_root=project_root, pilot_home=pilot_home, write=True)


def _access_denial(
    path: Path,
    *,
    project_root: Path,
    pilot_home: Path,
    write: bool,
) -> str | None:
    resolved = path.expanduser().resolve()
    project = project_root.expanduser().resolve()
    home = Path.home().resolve()
    pilot = pilot_home.expanduser().resolve()

    if resolved.name in BLOCKED_PROJECT_ENV_BASENAMES and _inside(resolved, project):
        action = "write" if write else "read"
        return (
            f"Access denied: refusing to {action} secret-bearing environment "
            f"file {resolved.name}."
        )

    if _inside(resolved, pilot) and resolved.name in BLOCKED_PILOT_HOME_FILES:
        action = "write" if write else "read"
        return f"Access denied: refusing to {action} Pilot Agent credential store {resolved.name}."

    if resolved.parent == home and resolved.name in BLOCKED_HOME_FILES:
        action = "write" if write else "read"
        return f"Access denied: refusing to {action} sensitive home file {resolved.name}."

    for dirname in BLOCKED_HOME_DIRS:
        blocked = home / dirname
        if _inside(resolved, blocked):
            action = "write" if write else "read"
            return f"Access denied: refusing to {action} sensitive directory {dirname}/."

    return None


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents
