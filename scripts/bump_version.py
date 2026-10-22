#!/usr/bin/env python3
"""Bump the ADVP patch/minor/major version and update release records.

This script does not commit. It updates:
  - VERSION
  - CHANGELOG.md (new release section under Unreleased)
  - package.json
  - docs/需求说明书.md (document control + revision row)

Usage:
  python scripts/bump_version.py --message "docs: clarify threshold"
  python scripts/bump_version.py --type minor --message "feat: add v1 baseline"
  python scripts/bump_version.py --dry-run --message "test"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def latest_release(changelog: str) -> str:
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, flags=re.MULTILINE)
    if not match:
        raise SystemExit("CHANGELOG.md has no versioned release")
    return match.group(1)


def bump(version: str, kind: str) -> str:
    match = SEMVER.match(version)
    if not match:
        raise SystemExit(f"VERSION is not SemVer: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=("patch", "minor", "major"), default="patch")
    parser.add_argument("--message", required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    message = args.message.strip()
    if not message:
        raise SystemExit("message must not be empty")

    version_file = ROOT / "VERSION"
    changelog_file = ROOT / "CHANGELOG.md"
    package_file = ROOT / "package.json"
    srs_file = ROOT / "docs" / "需求说明书.md"

    current = version_file.read_text(encoding="utf-8").strip()
    changelog = changelog_file.read_text(encoding="utf-8")
    if latest_release(changelog) != current:
        raise SystemExit(
            "VERSION and CHANGELOG are out of sync; run scripts/check_version.py first"
        )

    new_version = bump(current, args.type)
    print(f"version: {current} -> {new_version}")

    if args.dry_run:
        print("dry run: no files changed")
        return 0

    version_file.write_text(new_version + "\n", encoding="utf-8")

    release = f"## [{new_version}] - {args.date}\n\n### Changed\n\n- {message}\n"
    marker = "## [Unreleased]\n"
    if marker not in changelog:
        raise SystemExit("CHANGELOG.md is missing the '## [Unreleased]' marker")
    changelog = changelog.replace(marker, marker + "\n" + release, 1)
    changelog_file.write_text(changelog, encoding="utf-8")

    pkg = json.loads(package_file.read_text(encoding="utf-8"))
    pkg["version"] = new_version
    package_file.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    srs = srs_file.read_text(encoding="utf-8")
    srs = re.sub(r"\| 文档版本 \| v[0-9.]+ \|", f"| 文档版本 | v{new_version} |", srs, count=1)
    pattern = r"(\| 版本 \| 日期 \| 变更摘要 \| 变更人 \| 确认状态 \|\r?\n\|[-\s|]+\|\r?\n)"
    row = f"| v{new_version} | {args.date} | {message} | ADVP 项目组 | 待确认 |\n"
    if re.search(pattern, srs):
        srs = re.sub(pattern, lambda m: m.group(1) + row, srs, count=1)
    else:
        print("WARN: revision table not found; add the revision row manually")
    srs_file.write_text(srs, encoding="utf-8")

    print("updated: VERSION, CHANGELOG.md, package.json, docs/需求说明书.md")
    print("next steps:")
    print("  1. powershell -ExecutionPolicy Bypass -File scripts/build_docx.ps1")
    print(f"  2. git add -A && git commit -m \"{message}\"")
    print(f"  3. git tag v{new_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
