"""Confluence's `body-format=storage` is XHTML — this turns it into plain
text good enough to feed a summarization prompt. Not a rendering-quality
HTML parser: no BeautifulSoup/lxml dependency exists in this project
(pyproject.toml), and a summarization prompt only needs the visible text,
not structure. A regex-based strip is the smallest correct tool for that.
"""

from __future__ import annotations

import html
import re

_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_SPACE_AROUND_NEWLINE = re.compile(r"[ \t]*\n[ \t]*")
_MULTI_NEWLINE = re.compile(r"\n{2,}")
_MULTI_SPACE = re.compile(r"[ \t]+")


def strip_html(raw: str, *, max_chars: int = 8000) -> str:
    """Visible text only, entities decoded, collapsed whitespace, truncated
    to `max_chars` (bounds the LLM prompt size — a page body is otherwise
    unbounded, and ADR-003 already treats "unbounded vendor content" as
    something this project never persists or forwards wholesale)."""
    if not raw:
        return ""
    without_script = _SCRIPT_OR_STYLE.sub(" ", raw)
    without_tags = _TAG.sub(" ", without_script)
    decoded = html.unescape(without_tags)
    tightened_newlines = _SPACE_AROUND_NEWLINE.sub("\n", decoded)
    single_blank_lines = _MULTI_NEWLINE.sub("\n", tightened_newlines)
    collapsed_spaces = _MULTI_SPACE.sub(" ", single_blank_lines)
    return collapsed_spaces.strip()[:max_chars]
