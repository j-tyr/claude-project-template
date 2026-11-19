# Claude project wrapper template

A convention for keeping Claude Code's project memory, notes and tools in one durable
place, so that any new session (on your machine, or in a fresh Docker sandbox pointed at
the same directory) picks up where the last one stopped. It works with or without Docker
sandboxes (`sbx`).

## Why

- Notes, decisions and Claude's memory need to outlive any one session or sandbox, and be
  backed up, without cluttering the project repos.
- `/tmp` and Claude's session scratchpad are throwaway. Durable tooling needs a home.
- Multi-repo projects are awkward when each repo has its own Claude session.
- In a sandbox, only the mounted directory persists. `~/.claude` and parent directories
  you see inside the VM are VM-local, not your host's.

## Requirements

- [uv](https://docs.astral.sh/uv/), on your machine and in any sandbox (the sbx Claude image
  includes it), on the `PATH` Claude Code is started with. The scripts are standard-library
  Python run with `uv run --script`, which finds or downloads a suitable interpreter. If uv
  is missing or fails, the session start hook tells Claude it couldn't run.
- Python 3.11+ (`requires-python` in each script): the oldest version not yet at
  [end of life](https://devguide.python.org/versions/). Raise it in `wrapper.py` and
  `template/.state/session_start.py` when 3.11 reaches end of life.
- git, unless you create wrappers with `--no-git`.

## Layout

```
myproj/                         <- the wrapper: start Claude / the sandbox HERE
  CLAUDE.md                     wrapper rules, repo map, your project-specific prefs
  .ignore                       lets search tools (Claude's Grep) see the repos
  .claude/
    settings.json               session start hook + your project-specific rules
    settings.local.json         this machine's memory path + "don't ask again" approvals
  .state/
    notes/
      index.md                  lists every note
      recap.md                  overwritten handoff; printed at session start
      decisions.md              append-only decision log
      topics/  exports/         durable notes; conversations saved with /export
      drafts/                   not to commit for now; NOT in git
    memory/                     Claude's auto-memory
    tools/                      durable scripts, including sandbox_venvs.py
    sandbox-venvs.txt           repos that need a Python venv inside a sandbox
    session_start.py            prints the recap, checks the memory setting
  repoA/  repoB/                ordinary project repos, ignored by the wrapper
```

The wrapper is a git repo too. It ignores every visible top-level folder (the repos) and
tracks the rest: top-level files and the `.claude/` and `.state/` folders, except
`settings.local.json` and the contents of `drafts/`. Keep wrapper content in those
dot-folders, since any new visible top-level folder is treated as a repo. Push the wrapper
to a private remote to back up notes and memory without touching the project repos'
history. Single-repo projects use the same shape. Because git ignores the repos, so would Claude's Grep (it respects `.gitignore`);
`.ignore` re-includes them for search only.

## Usage

Run these on your own machine, from this toolkit's directory.

```bash
# Create a wrapper, with a remote for backing it up (or --no-git to skip git entirely)
uv run wrapper.py create --remote git@github.com:me/myproj-state.git ~/Documents/sandboxes/myproj

# Add the project repos, then start Claude (or a sandbox) in the wrapper
git -C ~/Documents/sandboxes/myproj clone <repo-url>

# Back up notes and memory (from a sandbox too, if GitHub access is enabled; see below)
git -C ~/Documents/sandboxes/myproj push -u origin HEAD

# On another machine, or after moving a wrapper
git clone git@github.com:me/myproj-state.git ~/work/myproj
uv run wrapper.py setup ~/work/myproj
```

- `create` does its git work locally (`init`, the first commit, adding the remote), so no
  credentials are needed until you push. The commit needs a git identity; without one,
  `create` warns and tells you how to commit later. With `--no-git` it skips git, and you can
  `git init` later with the same result.
- `setup` is needed because `autoMemoryDirectory` must be an absolute path (Claude Code
  doesn't expand variables in settings, and `~` differs between your Mac and a sandbox VM).
  So it's per machine, in the gitignored `settings.local.json`. `setup` writes it there and
  keeps any other settings. Sandboxes mount at the same path as your Mac, so one value serves
  both.
- **GitHub access from a sandbox is optional.** Without it, a sandbox works as normal but
  can't fetch private repos or push; do those from your Mac. To enable it, give sbx a token
  on your Mac (it injects credentials for HTTPS remotes only, so SSH remotes still won't work
  in a sandbox):
  ```bash
  sbx secret set github -t "$(gh auth token)"                     # sandboxes created from now on
  sbx secret set github --sandbox <name> -t "$(gh auth token)"    # one existing sandbox
  ```
- The template sets `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` so that each Bash command
  starts from the wrapper root: a stray `cd` into a non-repo folder would otherwise send
  later git commands to the wrapper's own repo.

To test the toolkit itself (the settings stop pytest writing caches into it):

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --python 3.11 --with pytest pytest tests/ -p no:cacheprovider
```

## Where instructions go

### Personal configuration

Your own preferences, rules and skills live at Claude Code's **user level**:

| Kind | Without sbx | In an sbx sandbox (only if you want it there) |
|---|---|---|
| **Prefs**: always-on defaults (git habits, code and comment style) | `~/.claude/CLAUDE.md` | Paste into the wrapper `CLAUDE.md`, "Working preferences for this project" |
| **Rules**: permissions and hooks that must hold | `~/.claude/settings.json` | Copy into the wrapper `.claude/settings.json` |
| **Skills**: procedures and how-tos | `~/.claude/skills/` | `sbx skills import` (copies your host skills) or `sbx skills add <repo>` |

Sandboxes deliberately don't import `~/.claude`; only project files and sbx's shared skills
store reach them. sbx also runs Claude Code in `bypassPermissions` mode, so without rules
copied into the project a sandbox session has none of your guardrails. Explicit `ask` and
`deny` rules in the wrapper's `.claude/settings.json` are still enforced in that mode.

To choose a kind, ask in this order:
1. Would breaking it be a real problem? Make it a **rule**. Only permissions and hooks guarantee anything.
2. Should it shape everything Claude writes, even unprompted? Make it a **pref** (e.g. docstring style).
3. Is it a how-to for a particular task? Make it a **skill**, with a one-line pointer among your
   prefs, because a skill loads only when Claude judges it relevant.

Keep prefs short and written as defaults; they're in context every session.

### Project configuration

| Kind | Where |
|---|---|
| Your project-specific prefs (override user-level ones; name the default replaced) | Wrapper `CLAUDE.md`, "Working preferences for this project" |
| Your project-specific rules | Wrapper `.claude/settings.json` |
| Team conventions | Each repo's own `CLAUDE.md` and `.claude/skills/` |
| Team hard rules, also catching commits made without Claude | Git hooks in the repo |
| Current state and history | `.state/notes/recap.md`, `decisions.md` |
| Other notes | `.state/notes/topics/`, `exports/`, `drafts/` |
| Learned facts | Auto-memory (`.state/memory/`) |
| Reusable tooling | `.state/tools/` |

Claude reconciles all of these by judgement; there's no strict precedence, which works
when prefs are written as defaults and overrides name what they replace. Permission rules
from every settings file combine (`deny` beats `ask` beats `allow`).

### Repos' own config (the multi-repo gap)

> **Warning.** Claude Code reads `.claude/settings.json` and `.mcp.json` only from the
> directory it was started in: the wrapper. A repo's own permission rules, hooks and MCP
> servers therefore **don't apply** in wrapper sessions, and nothing loads or merges them.
> Repos' `CLAUDE.md` and skills, by contrast, do load when Claude works in that repo.

Few repos ship this config, and missing it mostly means extra permission prompts. When you
clone a repo that has some, mirror what matters into the wrapper's config by hand (a repo
hook using `$CLAUDE_PROJECT_DIR` may need its path adjusted, since that variable points at
the wrapper). Two more options:
- `/cd repoA` (Claude Code v2.1.246+) switches the session to that repo's project files.
  The wrapper's settings, including the memory path, stop applying until you `/cd` back.
- `claude --settings repoA/.claude/settings.json` adds one repo's settings for a session
  (untested; in sbx, pass it after `--`).

## Python in a sandbox

A `.venv` created in a repo inside a sandbox holds Linux binaries, which break your macOS
tooling in the same directory. So list each Python repo in `.state/sandbox-venvs.txt`, and
in a sandbox **Claude** runs `uv run --script .state/tools/sandbox_venvs.py` before Python work
(the template `CLAUDE.md` tells it to). That runs `uv sync --frozen` for each repo into
`~/venvs/<project>/<repo>` in the VM and prints which venv is whose. Anything after a repo's
name in the file is passed to `uv sync`: use `repoA --extra dev` when a repo keeps its test
dependencies in an extra rather than a dependency group. On your Mac, use
`repo/.venv` as usual. Nothing enforces this: a stray plain `uv run` in a sandbox would
replace a repo's `.venv`, and you'd notice when your Mac tooling breaks there.

## Things to know

- **Start Claude from the wrapper root**, or the wrapper's settings, hook and memory don't load.
- **Session start output goes into Claude's context**, so keep the recap short (it's cut at
  6,000 characters). The hook runs on every session start, including after `/clear`,
  compaction and forks. A new sandbox's first session may download Python for it.
- **Sandbox detection** (in `sandbox_venvs.py`) relies on sbx setting `$SANDBOX_NAME`, which
  Docker doesn't document; check it after an sbx upgrade.
- **Transcripts** (`claude --resume`) live in `~/.claude`, so they're lost when a sandbox is
  removed. That's deliberate: the recap, decisions and memory are the curated record. To keep
  a conversation, `/export` it into `.state/notes/exports/` and add it to `index.md`.
- **`settings.local.json` isn't committed**: it's per machine, Claude Code saves approvals
  there (which can contain full commands, secrets included), and a tracked copy would wait for
  workspace trust. Approvals worth keeping belong in `settings.json`.
- **Nothing in `.state/` should be secret**, including the memory Claude writes there: the
  wrapper is pushed. Skim `.state/memory/` now and then.
