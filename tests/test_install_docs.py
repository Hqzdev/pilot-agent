from __future__ import annotations

import subprocess
from pathlib import Path


def test_install_scripts_have_valid_shell_syntax() -> None:
    assert subprocess.run(["bash", "-n", "install.sh"], check=False).returncode == 0
    assert subprocess.run(["bash", "-n", "setup-dev.sh"], check=False).returncode == 0


def test_install_script_uses_user_local_bin_not_usr_local() -> None:
    text = Path("install.sh").read_text(encoding="utf-8")

    assert "$HOME/.local/bin" in text
    assert "/usr/local/bin/pilot-agent" not in text
    assert "docker compose" in text


def test_readme_documents_onboarding_commands() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    for snippet in [
        "pilot-agent setup",
        "pilot-agent doctor",
        "pilot-agent model <provider>:<model>",
        "pilot-agent lessons clear",
        "/model",
        "/compact",
        "STATE.md",
    ]:
        assert snippet in readme
