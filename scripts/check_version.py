#!/usr/bin/env python3
"""Verify that VERSION, CHANGELOG, package.json, and SRS agree."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    version_file = ROOT / "VERSION"
    changelog = ROOT / "CHANGELOG.md"
    srs = ROOT / "docs" / "需求说明书.md"
    docx = ROOT / "docs" / "需求说明书.docx"
    package = ROOT / "package.json"

    for path in (version_file, changelog, srs, docx, package):
        if not path.exists():
            fail(f"missing {path.relative_to(ROOT)}")

    version = version_file.read_text(encoding="utf-8").strip()
    if not SEMVER.match(version):
        fail(f"VERSION is not SemVer: {version!r}")

    changelog_text = changelog.read_text(encoding="utf-8")
    releases = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", changelog_text, flags=re.MULTILINE)
    if not releases:
        fail("CHANGELOG.md has no versioned release")
    if releases[0] != version:
        fail(f"CHANGELOG latest is {releases[0]}, VERSION is {version}")

    srs_text = srs.read_text(encoding="utf-8")
    if f"| 文档版本 | v{version} |" not in srs_text:
        fail(f"SRS document control does not declare v{version}")

    pkg = json.loads(package.read_text(encoding="utf-8"))
    if pkg.get("version") != version:
        fail(f"package.json version is {pkg.get('version')!r}, expected {version!r}")

    prototype = ROOT / "docs" / "prototype" / "index.html"
    if not prototype.exists():
        fail("missing docs/prototype/index.html")
    html = prototype.read_text(encoding="utf-8")
    for i in range(1, 11):
        if f'id="page-p{i:02d}"' not in html:
            fail(f"prototype missing page-p{i:02d}")

    print(f"OK: version {version} is consistent")
    print(f"  CHANGELOG releases: {len(releases)}")
    print(f"  SRS: {srs.relative_to(ROOT)}")
    print(f"  DOCX: {docx.relative_to(ROOT)} ({docx.stat().st_size} bytes)")
    print("  prototype: 10 pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
