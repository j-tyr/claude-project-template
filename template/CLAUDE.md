# __PROJECT__

<!-- One or two sentences: what this project is and what "done" looks like. -->

## Layout

This directory is a project wrapper: a git repo of its own for notes, memory, tools and
Claude config. The repos below are separate repos, ignored by it. Claude is started here,
not inside a repo; don't `/cd` into a repo unless the user asks (that switches to the
repo's settings, and memory stops being saved here).

| Path | What |
|---|---|
| `<repo>/` | <!-- each repo and its role --> |
| `.state/notes/` | Handoff notes (see "Notes") |
| `.state/memory/` | Claude's auto-memory |
| `.state/tools/` | Durable scripts and helpers |

Team-facing conventions belong in each repo's own CLAUDE.md; this file is for the wrapper.

## Working preferences for this project

<!-- How the user works on this project. These override user-level preferences where they
     conflict; each names the default it replaces. In a Docker sandbox, user-level config
     isn't available, so paste here any personal preferences that should apply.
     e.g. "Commit directly to main in this project (overrides: branch per change)" -->

## Rules

- Only this directory persists. `/tmp`, the scratchpad and, in a Docker sandbox, `~/.claude`
  are lost. Reusable scripts go in `.state/tools/`, never only in the scratchpad.
- Never put secrets in `.state/`; this wrapper is pushed to a git remote.
- In Bash, use absolute paths, `git -C <repo>` or a `( cd … )` subshell, never a bare `cd`.
  Each command starts from this directory anyway, and inside a folder that isn't a repo, git
  falls through to this wrapper's own repo.
- GitHub access from a Docker sandbox is optional. If a fetch or push fails for lack of
  credentials, tell the user once and carry on with local work; it isn't a fault.
- Never copy a hook or MCP server from a repo's own config into this wrapper's config unless
  the user has approved that exact command.
- **Python in a Docker sandbox:** never create a `.venv` inside a repo; its Linux binaries
  would break the user's macOS tooling. Before Python work, run
  `uv run --script .state/tools/sandbox_venvs.py`, then always use
  `UV_PROJECT_ENVIRONMENT=<venv> uv run --frozen --directory <repo> ...`. A plain `uv run`,
  `uv sync`, `uv add`, `uv venv` or `python -m venv .venv` in a repo would create or replace its
  `.venv`, and nothing blocks them. On the user's Mac, use the repo's own `.venv` as usual.

## Notes

The recap is printed at session start. `.state/notes/index.md` lists the rest.

- `recap.md`: **overwrite** at the end of a session with current state, next steps and open
  questions. Under a page.
- `decisions.md`: **append-only**, with date, decision and why. A decision that deserves a
  formal ADR goes in the relevant repo; leave a one-line pointer here.
- New notes go in a subdirectory, never at the top of `notes/`, and are listed in `index.md`:
  `topics/` for durable notes; `exports/` for `/export`ed conversations (check them for
  secrets); `drafts/` for docs not to commit for now (work in progress, learning material).
  Drafts are **not in git**.
- Stable facts and preferences go in auto-memory. Rules state the rule; the history behind
  them goes in `decisions.md`.
- After updating the recap, commit `.state/` in this wrapper (not in the project repos).
