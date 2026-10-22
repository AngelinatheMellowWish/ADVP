#!/usr/bin/env python3
"""Offline checks for docs/prototype/index.html.

Verifies structural integrity, duplicate ids, required pages, and absence of
external network dependencies. Exits non-zero on failure.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "docs" / "prototype" / "index.html"

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

REQUIRED_PAGES = [f"page-p{i:02d}" for i in range(1, 11)]


class Checker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []
        self.ids: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        for name, value in attrs:
            if name == "id" and value:
                if value in self.ids:
                    self.errors.append(
                        f"duplicate id '{value}' at line {line} "
                        f"(first seen line {self.ids[value]})"
                    )
                else:
                    self.ids[value] = line
        if tag not in VOID:
            self.stack.append((tag, line))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        line = self.getpos()[0]
        if not self.stack:
            self.errors.append(f"unexpected closing </{tag}> at line {line}")
            return
        open_tag, open_line = self.stack[-1]
        if open_tag == tag:
            self.stack.pop()
            return
        self.errors.append(
            f"mismatched </{tag}> at line {line}; expected </{open_tag}> "
            f"opened at line {open_line}"
        )
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx][0] == tag:
                del self.stack[idx:]
                return


def main() -> int:
    if not PROTOTYPE.exists():
        print(f"FAIL: missing {PROTOTYPE}")
        return 1

    html = PROTOTYPE.read_text(encoding="utf-8")
    checker = Checker()
    checker.feed(html)
    checker.close()

    errors = list(checker.errors)
    for tag, line in checker.stack:
        errors.append(f"unclosed <{tag}> opened at line {line}")

    for page_id in REQUIRED_PAGES:
        if f'id="{page_id}"' not in html:
            errors.append(f"missing required page section id='{page_id}'")

    external = re.findall(
        r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""",
        html,
        flags=re.IGNORECASE,
    )
    for url in external:
        errors.append(f"external dependency is not allowed in offline prototype: {url}")

    if errors:
        print("FAIL: prototype checks found issues")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("OK: prototype HTML is structurally valid")
    print(f"  pages: {len(REQUIRED_PAGES)}")
    print(f"  ids: {len(checker.ids)}")
    print(f"  size: {PROTOTYPE.stat().st_size} bytes")
    print("  external dependencies: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
