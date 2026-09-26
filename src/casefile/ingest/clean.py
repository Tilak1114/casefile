"""Turn Reducto blocks into page text the verifier can match quotes against.

Stored text keeps the document's own characters. Only markup Reducto adds is removed, and every
removal is counted so it can be shown and audited.
"""

import html
import re
from collections import Counter

from casefile.ingest.models import BlockSpan, ReductoBlock

# Model-written descriptions of images, not text on the page.
DROPPED_BLOCK_TYPES = {"Figure"}

_CELL_END = re.compile(r"</t[dh]>", re.I)
_ROW_END = re.compile(r"</tr>", re.I)
_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
_REDACTED = re.compile(r"\[Redacted\]")
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")


def clean_block(content: str) -> tuple[str, Counter]:
    removed: Counter = Counter()
    removed["table_cell"] += len(_CELL_END.findall(content))
    text = _CELL_END.sub(" ", content)
    removed["table_row"] += len(_ROW_END.findall(text))
    text = _ROW_END.sub("\n", text)

    def drop_tag(match: re.Match) -> str:
        removed[f"<{match.group(1).lower()}>"] += 1
        return ""

    text = _TAG.sub(drop_tag, text)
    removed["[Redacted]"] += len(_REDACTED.findall(text))
    text = _REDACTED.sub("", text)
    removed["entity"] += len(_ENTITY.findall(text))
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n")).strip()
    return text, +removed


def page_text(blocks: list[ReductoBlock]) -> tuple[str, list[BlockSpan], dict[str, int], int]:
    """Blocks of one page, in Reducto's reading order, to (text, spans, removed markup, figures dropped)."""
    parts: list[str] = []
    spans: list[BlockSpan] = []
    removed: Counter = Counter()
    figures = 0
    cursor = 0
    for block in blocks:
        if block.type in DROPPED_BLOCK_TYPES:
            figures += 1
            continue
        text, counts = clean_block(block.content)
        removed.update(counts)
        if not text:
            continue
        if parts:
            cursor += 1  # the newline joining blocks
        spans.append(BlockSpan(start=cursor, end=cursor + len(text), type=block.type, bbox=block.bbox))
        parts.append(text)
        cursor += len(text)
    return "\n".join(parts), spans, dict(removed), figures
