#!/usr/bin/env python3
"""Offline Markdown link checker for ADVP.

Checks local links in every Markdown file without network access. External URLs,
mail links, and pure anchors are skipped. Exits non-zero if a local target is
missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"node_modules", ".git", "build", "dist", ".venv", "venv"}
FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REF_LINK = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
SKIP_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "//",
    "#",
)


def markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def clean_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    # Drop an optional Markdown title: path "title"
    target = target.split()[0].strip()
    return target


def is_external(target: str) -> bool:
    lower = target.lower()
    return lower.startswith(SKIP_PREFIXES) or lower.startswith("data:")


def resolve(source: Path, target: str) -> Path | None:
    target = clean_target(target)
    if not target or is_external(target):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    target = unquote(target).replace("\\", "/")
    if not target:
        return None
    candidate = (ROOT / target.lstrip("/")) if target.startswith("/") else (source.parent / target)
    return candidate.resolve()


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = FENCE.sub("", text)
    text = re.sub(r"`[^`]*`", "", text)
    errors: list[str] = []
    targets: list[tuple[int, str]] = []
    for match in INLINE_LINK.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        targets.append((line, match.group(1)))
    for match in REF_LINK.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        targets.append((line, match.group(1)))
    for line, raw in targets:
        target = clean_target(raw)
        if is_external(target):
            continue
        resolved = resolve(path, target)
        if resolved is not None and not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}:{line}: missing link target {target!r}")
    return errors


def main() -> int:
    errors: list[str] = []
    files = markdown_files()
    for path in files:
        errors.extend(check_file(path))
    if errors:
        print("FAIL: broken local links")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK: checked {len(files)} Markdown files, no broken local links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
