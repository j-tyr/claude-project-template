"""Tests for wrapper.py and the template's scripts.

Run from the toolkit directory:
    PYTHONDONTWRITEBYTECODE=1 uv run --python 3.11 --with pytest pytest tests/ -p no:cacheprovider

Scripts are run as subprocesses, the way users and the hook run them, in pytest's tmp_path.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_DIR = Path(__file__).resolve().parent.parent
HOOK_COMMAND = json.loads((TOOLKIT_DIR / "template" / ".claude" / "settings.json").read_text())[
    "hooks"]["SessionStart"][0]["hooks"][0]["command"]


@pytest.fixture(autouse=True)
def git_identity(monkeypatch):
    # The initial commit needs an identity; don't depend on the machine's git config.
    for variable in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(variable, "Test")
    for variable in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(variable, "test@example.com")


def run(*command, env=None):
    return subprocess.run([str(part) for part in command], capture_output=True, text=True, env=env)


def wrapper_py(*args, env=None):
    return run(sys.executable, TOOLKIT_DIR / "wrapper.py", *args, env=env)


def session_start(wrapper):
    result = run(sys.executable, wrapper / ".state" / "session_start.py")
    assert result.returncode == 0 and "failed" not in result.stdout, result.stdout + result.stderr
    return result.stdout


def empty_dir(path):
    path.mkdir()
    return path


@pytest.fixture
def wrapper(tmp_path):
    project = tmp_path / "proj"
    result = wrapper_py("create", project)
    assert result.returncode == 0, result.stderr
    return project


# --- wrapper.py --------------------------------------------------------------------------

def test_create(wrapper):
    tracked = run("git", "-C", wrapper, "ls-files").stdout.split()
    for expected in (".ignore", ".state/session_start.py", ".state/tools/sandbox_venvs.py",
                     ".state/notes/drafts/.gitkeep"):
        assert expected in tracked
    assert ".claude/settings.local.json" not in tracked  # per machine
    settings = json.loads((wrapper / ".claude" / "settings.local.json").read_text())
    assert settings == {"autoMemoryDirectory": str(wrapper / ".state" / "memory")}
    assert (wrapper / "CLAUDE.md").read_text().startswith("# proj\n")
    assert "WARNING" not in session_start(wrapper)


def test_create_with_remote(tmp_path):
    result = wrapper_py("create", "--remote", "git@example.com:me/state.git", tmp_path / "proj")
    assert result.returncode == 0, result.stderr
    assert run("git", "-C", tmp_path / "proj", "remote", "get-url", "origin").stdout.strip() == "git@example.com:me/state.git"


def test_create_without_git(tmp_path):
    # Works even with no git installed, since it never calls git.
    no_git = {**os.environ, "PATH": str(empty_dir(tmp_path / "bin"))}
    result = wrapper_py("create", "--no-git", tmp_path / "proj", env=no_git)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "proj" / ".git").exists()
    assert (tmp_path / "proj" / ".claude" / "settings.local.json").is_file()


@pytest.mark.parametrize("args, message", [
    (["--no-git", "--remote", "x"], "--remote needs git"),
    ([], "not empty"),
])
def test_create_refuses(tmp_path, args, message):
    project = empty_dir(tmp_path / "proj")
    if not args:
        (project / "file").write_text("x")
    result = wrapper_py("create", *args, project)
    assert result.returncode == 1 and message in result.stderr
    assert list(project.iterdir()) == ([] if args else [project / "file"])  # nothing created


def test_git_ignores_the_repos_but_search_sees_them(wrapper):
    for repo in ("repoA", "group/repoB"):
        (wrapper / repo).mkdir(parents=True)
        (wrapper / repo / "file.txt").write_text("NEEDLE\n")
    (wrapper / ".state" / "notes" / "drafts" / "draft.md").write_text("x")
    (wrapper / ".state" / "notes" / "topics" / "topic.md").write_text("x")
    status = run("git", "-C", wrapper, "status", "--short", "--untracked-files=all").stdout
    assert status.strip() == "?? .state/notes/topics/topic.md"
    # Claude Code's Grep respects .gitignore, which ignores every repo; .ignore undoes that.
    if shutil.which("rg"):
        found = subprocess.run(["rg", "-l", "NEEDLE"], cwd=wrapper, capture_output=True, text=True).stdout.split()
        assert sorted(found) == ["group/repoB/file.txt", "repoA/file.txt"]


def test_setup_on_a_clone_keeps_other_settings(wrapper, tmp_path):
    clone = tmp_path / "clone"
    run("git", "clone", "-q", wrapper, clone)
    local = clone / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"autoMemoryDirectory": "/old", "permissions": {"allow": ["Bash(make)"]}}))
    assert wrapper_py("setup", clone).returncode == 0
    assert json.loads(local.read_text()) == {"autoMemoryDirectory": str(clone / ".state" / "memory"),
                                             "permissions": {"allow": ["Bash(make)"]}}
    assert (clone / ".state" / "notes" / "drafts").is_dir()


@pytest.mark.parametrize("content", [b"{not json", b"[1, 2]"])
def test_setup_refuses_invalid_settings(wrapper, content):
    local = wrapper / ".claude" / "settings.local.json"
    local.write_bytes(content)
    result = wrapper_py("setup", wrapper)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    assert local.read_bytes() == content


def test_setup_refuses_non_wrapper(tmp_path):
    result = wrapper_py("setup", tmp_path)
    assert result.returncode == 1 and "not a project wrapper" in result.stderr


# --- session_start.py --------------------------------------------------------------------

def test_recap_comes_first_and_is_truncated(wrapper):
    (wrapper / ".state" / "notes" / "recap.md").write_text("x" * 7000)
    output = session_start(wrapper)
    assert output.startswith("## Project recap")
    assert "x" * 6000 in output and "x" * 6001 not in output


@pytest.mark.parametrize("value", ['"/elsewhere"', "42"])
def test_memory_warning(wrapper, value):
    (wrapper / ".claude" / "settings.local.json").write_text(f'{{"autoMemoryDirectory": {value}}}')
    assert "memory is not configured" in session_start(wrapper)


def test_memory_check_follows_symlinks(wrapper, tmp_path):
    (tmp_path / "alias").symlink_to(wrapper)
    assert wrapper_py("setup", tmp_path / "alias").returncode == 0
    assert "WARNING" not in session_start(wrapper)


# --- the hook command --------------------------------------------------------------------

def run_hook(wrapper, path_dir):
    # /bin/sh by absolute path, so PATH can be exactly the directory under test.
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(wrapper), "PATH": str(path_dir)}
    return subprocess.run(["/bin/sh", "-c", HOOK_COMMAND], capture_output=True, text=True, env=env)


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")
def test_hook_runs_once_with_uv(wrapper):
    output = run_hook(wrapper, Path(shutil.which("uv")).parent).stdout
    assert output.startswith("## Project recap") and output.count("## Project recap") == 1
    assert "could not run" not in output


@pytest.mark.parametrize("uv_script", [None, "#!/bin/sh\nexit 1\n"], ids=["uv missing", "uv fails"])
def test_hook_tells_claude_when_uv_does_not_work(wrapper, tmp_path, uv_script):
    bin_dir = empty_dir(tmp_path / "bin")
    if uv_script:
        (bin_dir / "uv").write_text(uv_script)
        (bin_dir / "uv").chmod(0o755)
    output = run_hook(wrapper, bin_dir).stdout
    assert "session start hook could not run" in output and "Project recap" not in output


# --- tools/sandbox_venvs.py --------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "linux", reason="only runs in a (Linux) sandbox")
def test_sandbox_venvs_build_outside_the_mount(wrapper, tmp_path):
    # The stub fails for repoB and records the venv location it was given for the others,
    # so this fails if the location (the whole point: outside the mount) isn't passed to uv.
    bin_dir = empty_dir(tmp_path / "bin")
    (bin_dir / "uv").write_text(
        '#!/bin/sh\ncase "$*" in *repoB*) echo "error: no lockfile" >&2; exit 2;; esac\n'
        'echo "$UV_PROJECT_ENVIRONMENT" > "$UV_PROJECT_ENVIRONMENT.seen"\n'
    )
    (bin_dir / "uv").chmod(0o755)
    for repo in ("repoA", "repoB"):
        (wrapper / repo).mkdir()
    (wrapper / ".state" / "sandbox-venvs.txt").write_text("repoA\r\n# comment\nrepoB\n")
    venv_root = tmp_path / "home" / "venvs" / "proj"
    venv_root.mkdir(parents=True)
    env = {**os.environ, "SANDBOX_NAME": "test", "HOME": str(tmp_path / "home"), "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    result = run(sys.executable, wrapper / ".state" / "tools" / "sandbox_venvs.py", env=env)
    assert f"- repoA: {venv_root / 'repoA'}" in result.stdout
    assert (venv_root / "repoA.seen").read_text().strip() == str(venv_root / "repoA")
    assert "- repoB: FAILED" in result.stdout and "error: no lockfile" in result.stderr
    assert "comment" not in result.stdout and result.returncode == 1


def test_sandbox_venvs_refuse_outside_a_sandbox(wrapper):
    env = {key: value for key, value in os.environ.items() if key != "SANDBOX_NAME"}
    result = run(sys.executable, wrapper / ".state" / "tools" / "sandbox_venvs.py", env=env)
    assert result.returncode == 1 and "not in a Docker sandbox" in result.stdout
