#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Prepare a Claude session in this project wrapper; run by the SessionStart hook.

Claude Code adds this script's stdout to the session context, so it prints only:
    1. The recap (.state/notes/recap.md), truncated if long.
    2. A warning if this machine's .claude/settings.local.json doesn't point Claude's
       memory at this wrapper's .state/memory (fixed by the toolkit's `wrapper.py setup`).

Usage:
    uv run --script .state/session_start.py

Side effects: none. It only reads files and prints.
"""

import json
import os
import sys
from pathlib import Path

# Deliberately not resolve(): keep the path Claude Code uses for the project directory.
PROJECT_DIR = Path(os.path.abspath(__file__)).parent.parent
STATE_DIR = PROJECT_DIR / ".state"
LOCAL_SETTINGS = PROJECT_DIR / ".claude" / "settings.local.json"
RECAP_FILE = STATE_DIR / "notes" / "recap.md"

RECAP_MAX_CHARS = 6000  # Claude Code shows only a preview of hook output over 10,000
DETAIL_MAX_CHARS = 200  # for other text taken from files or errors


def print_recap() -> None:
    """Print the recap first, so it reaches Claude even if the memory check fails."""
    if not RECAP_FILE.is_file():
        return
    recap = RECAP_FILE.read_text(encoding="utf-8", errors="replace")
    print("## Project recap (.state/notes/recap.md)")
    print(recap[:RECAP_MAX_CHARS])
    if len(recap) > RECAP_MAX_CHARS:
        print(
            f"[Recap truncated at {RECAP_MAX_CHARS} of {len(recap)} characters: read the file "
            "for the rest, and shorten it at the next handoff.]"
        )
    print()


def check_memory_setting() -> None:
    """Warn unless autoMemoryDirectory names this wrapper's .state/memory."""
    expected = STATE_DIR / "memory"
    configured = None
    if LOCAL_SETTINGS.is_file():
        try:
            configured = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8")).get("autoMemoryDirectory")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            configured = "(settings.local.json is not a valid JSON object)"
    # samefile, not string comparison: the wrapper may be reached through a symlink.
    if isinstance(configured, str) and Path(configured).is_dir() and expected.is_dir():
        if os.path.samefile(configured, expected):
            return
    print("## WARNING: memory is not configured for this wrapper on this machine")
    print(f"Expected .claude/settings.local.json to set autoMemoryDirectory to\n  {expected}")
    print(f"but found: {str(configured)[:DETAIL_MAX_CHARS] if configured else '(not set)'}")
    print(
        "Memory from this session will not be saved in the wrapper. Tell the user; the fix is\n"
        "to run `uv run wrapper.py setup <this wrapper>` from the template toolkit on their\n"
        "machine (the toolkit isn't available inside a sandbox), then restart Claude.\n"
    )


def main() -> int:
    # A failure in one section is reported, but never stops the other.
    for section in (print_recap, check_memory_setting):
        try:
            section()
        except Exception as error:
            print(f"[session_start.py: {section.__name__} failed: {str(error)[:DETAIL_MAX_CHARS]}]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
