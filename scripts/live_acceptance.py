from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def main() -> int:
    missing = prerequisites()
    if missing:
        print(json.dumps({"ready": False, "missing": missing}, indent=2))
        return 0
    with tempfile.TemporaryDirectory(prefix="pilot-agent-live-") as tmp:
        project = Path(tmp)
        write_next_app(project)
        deploy = subprocess.run(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "--entrypoint",
                "bash",
                "-v",
                f"{project}:/live-workspace",
                "pilot-agent",
                "-lc",
                live_command(),
            ],
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
    url = extract_vercel_url(deploy.stdout + "\n" + deploy.stderr)
    status = probe(url) if url else None
    print(
        json.dumps(
            {
                "ready": True,
                "exit_code": deploy.returncode,
                "production_url": url,
                "http_status": status,
                "stdout_tail": tail(deploy.stdout),
                "stderr_tail": tail(deploy.stderr),
            },
            indent=2,
        )
    )
    return 0 if deploy.returncode == 0 and status == 200 else 1


def prerequisites() -> list[str]:
    missing: list[str] = []
    if shutil.which("docker") is None:
        missing.append("docker")
    elif subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0:
        missing.append("docker compose access")
    if not any(os.environ.get(key) for key in provider_keys()):
        missing.append("ANTHROPIC_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY")
    if not os.environ.get("VERCEL_TOKEN"):
        missing.append("VERCEL_TOKEN")
    return missing


def provider_keys() -> tuple[str, ...]:
    return ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")


def write_next_app(project: Path) -> None:
    (project / "app").mkdir(parents=True)
    (project / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"build": "next build"},
                "dependencies": {"next": "latest", "react": "latest", "react-dom": "latest"},
                "devDependencies": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (project / "app" / "page.tsx").write_text(
        "export default function Page() { return <main>Hello Pilot Agent</main>; }\n",
        encoding="utf-8",
    )


def live_command() -> str:
    return (
        "set -euo pipefail; "
        "cp -R /live-workspace/. /workspace; "
        "npm install; "
        "npm run build; "
        "vercel --prod --yes --token \"$VERCEL_TOKEN\""
    )


def extract_vercel_url(output: str) -> str | None:
    matches = re.findall(r"https://[a-zA-Z0-9.-]+\\.vercel\\.app", output)
    return matches[-1] if matches else None


def probe(url: str | None) -> int | None:
    if url is None:
        return None
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.status
    except OSError:
        return None


def tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.splitlines()[-lines:])


if __name__ == "__main__":
    sys.exit(main())
