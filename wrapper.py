#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create project wrappers, and set up existing ones on this machine.

A project wrapper is a directory that holds one or more project repos plus a small git
repo of its own for notes, Claude memory, tools and Claude config. Point Claude (or a
Docker sandbox) at the wrapper, then clone the project repos inside it.

Claude's memory location is an absolute path, so it is per machine: it lives in the
wrapper's gitignored .claude/settings.local.json. `create` writes it for a new wrapper;
`setup` writes it for an existing wrapper that was cloned onto this machine, or moved.

Usage:
    uv run wrapper.py create [--remote URL | --no-git] PROJECT_DIR
    uv run wrapper.py setup PROJECT_DIR

Examples:
    uv run wrapper.py create ~/Documents/sandboxes/myproj
    uv run wrapper.py create --remote git@github.com:me/myproj-state.git ~/Documents/sandboxes/myproj
    uv run wrapper.py create --no-git ~/Documents/sandboxes/scratch
    git clone git@github.com:me/myproj-state.git ~/work/myproj
    uv run wrapper.py setup ~/work/myproj

Side effects:
    create: makes PROJECT_DIR, copies ./template into it and sets the memory path in
        .claude/settings.local.json. Unless --no-git is given, it also runs `git init` and an
        initial commit, and optionally adds a remote; all local, so no credentials needed.
    setup: sets the memory path in PROJECT_DIR/.claude/settings.local.json, keeping every
        other setting in that file.
    Never pushes, never deletes anything.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

TOOLKIT_DIR = Path(os.path.abspath(__file__)).parent
TEMPLATE_DIR = TOOLKIT_DIR / "template"
TEMPLATE_IGNORE = shutil.ignore_patterns(".DS_Store", "__pycache__")  # Finder and Python litter


class ToolkitError(Exception):
    """A problem to report to the user as a one-line error, without a traceback."""


def configure_memory(project_dir: Path) -> None:
    """Set autoMemoryDirectory in the wrapper's settings.local.json, keeping other keys.

    Claude Code also saves "don't ask again" approvals in this file, so it is updated
    rather than overwritten.
    """
    settings_file = project_dir / ".claude" / "settings.local.json"
    memory_dir = str(project_dir / ".state" / "memory")

    settings = {}
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ToolkitError(f"{settings_file} is not valid JSON ({error}); fix it first")
        if not isinstance(settings, dict):
            raise ToolkitError(f"{settings_file} does not contain a JSON object; fix it first")

    if settings.get("autoMemoryDirectory") == memory_dir:
        print(f"Memory already configured in {settings_file}")
        return
    settings["autoMemoryDirectory"] = memory_dir
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"Set memory path in {settings_file}")


def git(project_dir: Path, *args: str) -> bool:
    return subprocess.run(["git", "-C", str(project_dir), *args]).returncode == 0


def setup(project_dir: Path) -> None:
    """Set this machine's memory path in an existing wrapper (after cloning or moving it)."""
    if not (project_dir / ".state" / "session_start.py").is_file():
        raise ToolkitError(f"not a project wrapper (no .state/session_start.py): {project_dir}")
    configure_memory(project_dir)
    print(f"Done. Start Claude (or a sandbox) from {project_dir}.")


def create(project_dir: Path, remote_url: str | None, use_git: bool) -> None:
    """Create a wrapper at project_dir from the template.

    With use_git False, the wrapper is left as plain files; its .gitignore is still in
    place, so `git init` later works as if it had been done here.
    """
    # Checked first, so these mistakes leave nothing behind.
    if remote_url and not use_git:
        raise ToolkitError("--remote needs git; drop --no-git, or add the remote later")
    if project_dir.exists() and any(project_dir.iterdir()):
        raise ToolkitError(f"refusing: {project_dir} exists and is not empty")
    if use_git and shutil.which("git") is None:
        raise ToolkitError("git is not installed or not on PATH (use --no-git to skip git)")

    # dirs_exist_ok: project_dir may already exist, if empty.
    shutil.copytree(TEMPLATE_DIR, project_dir, dirs_exist_ok=True, ignore=TEMPLATE_IGNORE)
    claude_md = (TEMPLATE_DIR / "CLAUDE.md").read_text(encoding="utf-8")
    (project_dir / "CLAUDE.md").write_text(claude_md.replace("__PROJECT__", project_dir.name), encoding="utf-8")
    configure_memory(project_dir)

    quoted_dir = shlex.quote(str(project_dir))
    steps = [
        f"Clone the project repos inside it:  git -C {quoted_dir} clone <repo-url>",
        f"Edit {project_dir}/CLAUDE.md: describe the project and list the repos.",
        f"Python repos that need a venv inside a Docker sandbox: list them in {project_dir}/.state/sandbox-venvs.txt",
        f"Start Claude (or the sandbox) from {project_dir} itself, not from a repo inside it.",
    ]
    if use_git:
        sys.stdout.flush()  # keep our messages in order with git's
        git(project_dir, "init", "--quiet")
        git(project_dir, "add", "--all")
        if not git(project_dir, "commit", "--quiet", "-m", "Initialise project wrapper"):
            print("wrapper.py: warning: initial commit failed (is git user.name/user.email set?)", file=sys.stderr)
            steps.append(f"Make the initial commit:  git -C {quoted_dir} commit -m 'Initialise project wrapper'")
        if remote_url:
            git(project_dir, "remote", "add", "origin", remote_url)
            steps.append(f"Back up notes and memory:  git -C {quoted_dir} push -u origin HEAD")
    else:
        steps.append(f"To back up notes and memory later:  git -C {quoted_dir} init, then add and commit")

    print(f"\nCreated project wrapper: {project_dir}\n\nNext steps:")
    for number, step in enumerate(steps, start=1):
        print(f"  {number}. {step}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="wrapper.py",
        description="Create project wrappers, and set up existing ones on this machine.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    create_parser = commands.add_parser("create", help="create a new wrapper from the template")
    create_parser.add_argument("project_dir", help="directory to create (it must not exist, or be empty)")
    create_parser.add_argument("--remote", metavar="URL", help="add URL as the wrapper's 'origin' remote")
    create_parser.add_argument(
        "--git",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="make the wrapper a git repo with an initial commit (default: yes)",
    )

    setup_parser = commands.add_parser("setup", help="set up an existing wrapper on this machine")
    setup_parser.add_argument("project_dir", help="an existing project wrapper")

    args = parser.parse_args()
    # Deliberately not Path.resolve(): resolving symlinks (e.g. macOS /tmp -> /private/tmp)
    # would record a different path from the one you gave and will start Claude from.
    project_dir = Path(os.path.abspath(os.path.expanduser(args.project_dir)))
    try:
        if args.command == "create":
            create(project_dir=project_dir, remote_url=args.remote, use_git=args.git)
        else:
            setup(project_dir)
    except (ToolkitError, OSError) as error:
        print(f"wrapper.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
