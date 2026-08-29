#!/usr/bin/env python3
"""Escape bare angle brackets in generated VitePress pages.

The canonical docs use `<host>`, `<gid>`, `<favcat>`, `<host-folder>` … as
plain text (GitHub wiki renders them literally). VitePress treats `<word>` as
HTML, so those must be escaped as `\\<word>` — which renders identically.
Real HTML tags (images, tables) are kept. Fenced code blocks and inline code
are left untouched.
"""

import pathlib
import re
import sys

ALLOWED = {
    "a", "b", "blockquote", "br", "button", "center", "code", "div",
    "details", "em", "figcaption", "figure", "h1", "h2", "h3", "h4", "h5",
    "h6", "hr", "i", "iframe", "img", "input", "kbd", "label", "li",
    "option", "p", "pre", "select", "source", "span", "strong", "sub",
    "summary", "sup", "table", "tbody", "td", "th", "thead", "tr", "ul",
    "video",
}

TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)([^>]*)>")


def escape_line(line: str) -> str:
    out = []
    i, n = 0, len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = line[i:j]
            out.append(run)
            k = line.find(run, j)
            if k != -1:
                out.append(line[j:k])
                out.append(run)
                i = k + len(run)
            else:
                i = j
            continue
        if line[i] == "<":
            m = TAG_RE.match(line, i)
            if m and m.group(1).lower() in ALLOWED:
                out.append(m.group(0))
                i += len(m.group(0))
                continue
            close = line.find(">", i + 1)
            if close != -1:
                inner = line[i + 1 : close]
                if inner and not inner[0].isspace():
                    out.append("\\<" + inner + ">")
                    i = close + 1
                    continue
            out.append(line[i])
            i += 1
            continue
        out.append(line[i])
        i += 1
    return "".join(out)


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "src")
    for md in sorted(root.glob("*.md")):
        lines = md.read_text(encoding="utf-8").split("\n")
        in_fence = False
        out = []
        for line in lines:
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                out.append(line)
            elif in_fence:
                out.append(line)
            else:
                out.append(escape_line(line))
        md.write_text("\n".join(out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
