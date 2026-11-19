#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build this wrapper's Python venvs inside a Docker sandbox, outside the mounted directory.

Inside a sandbox, a repo's .venv would hold Linux binaries in the same directory the
user's macOS tooling uses, breaking it. So for each repo listed in .state/sandbox-venvs.txt,
this runs `uv sync --frozen` into ~/venvs/<project>/<repo> in the VM and prints which venv
belongs to which repo. Claude runs it before Python work in a sandbox. Anything after the
repo name on its line is passed to `uv sync`, e.g. `repoA --extra dev`.

Usage:
    uv run --script .state/tools/sandbox_venvs.py

Then, for each repo:
    UV_PROJECT_ENVIRONMENT=<venv> uv run --frozen --directory <repo> <command>

Side effects: creates or updates venvs under ~/venvs/<project>/ in the sandbox VM.
"""

import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(os.path.abspath(__file__)).parent.parent.parent
VENV_LIST_FILE = PROJECT_DIR / ".state" / "sandbox-venvs.txt"
VENV_ROOT = Path.home() / "venvs" / PROJECT_DIR.name


def main() -> int:
    # sbx sets SANDBOX_NAME in its VMs (undocumented by Docker; re-check after upgrades).
    if platform.system() != "Linux" or not os.environ.get("SANDBOX_NAME"):
        print("sandbox_venvs.py: not in a Docker sandbox; on the host, use repo/.venv as usual.")
        return 1

    # Each entry is the repo name and any extra `uv sync` arguments, e.g. ["repoA", "--extra", "dev"].
    entries = [
        shlex.split(line)  # also removes a Windows \r line ending
        for line in VENV_LIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not entries:
        print(f"No repos listed in {VENV_LIST_FILE}; add each Python repo's folder name, one per line.")
        return 1

    failed = []
    for repo, *uv_args in entries:
        venv_dir = VENV_ROOT / repo
        # --frozen: install exactly what the lockfile says, never re-lock. --quiet: only
        # errors are printed, so Claude sees what went wrong and nothing else.
        result = subprocess.run(
            ["uv", "sync", "--frozen", "--quiet", "--directory", str(PROJECT_DIR / repo), *uv_args],
            env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv_dir)},
        )
        if result.returncode == 0:
            print(f"- {repo}: {venv_dir}")
        else:
            print(f"- {repo}: FAILED (see uv's error above)")
            failed.append(repo)

    print("\nUse, for each repo:\n  UV_PROJECT_ENVIRONMENT=<venv> uv run --frozen --directory <repo> <command>")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
