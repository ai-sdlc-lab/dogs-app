#!/usr/bin/env python3
"""PreToolUse hook: block agent edits to protected paths (exit 2 = block).

Protected paths are human- or reviewer-owned (CODEOWNERS); agents never edit them.
"""
import fnmatch
import json
import os
import sys

PROTECTED = [
    ".claude/*",
    "CLAUDE.md",
    "REVIEW.md",
    ".github/*",
    "docs/specs/*/THREAT-*.md",
    "docs/specs/*/TRACE-*.md",
]

event = json.load(sys.stdin)
path = event.get("tool_input", {}).get("file_path") or event.get("tool_input", {}).get("notebook_path") or ""
root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")
rel = os.path.relpath(os.path.realpath(os.path.join(root, path)), root)

# fnmatch's * also matches "/", so ".github/*" covers the whole subtree.
if rel.startswith("..") or any(fnmatch.fnmatch(rel, p) for p in PROTECTED):
    print(f"Blocked: {rel} is a protected path (see CODEOWNERS); agents may not edit it.", file=sys.stderr)
    sys.exit(2)
