"""What the output guardrail reads from a node: every word a learner will see.

Picking named fields — text, question, caption — left the rest unread, and the
rest is where a refused sentence goes next: a checklist item, a quiz option, an
image's alt text. So the screened text is every string in every block, except
the fields that are not prose: the block's type, an image's source, which goes
to the image screening, and citations, which are chunk ids.
"""
from __future__ import annotations

NOT_PROSE = {"type", "src", "cites"}


def blocks_of(content) -> list[dict]:
    blocks = content.get("blocks") if isinstance(content, dict) else None
    return [b for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []


def prose(value, key: str | None = None) -> list[str]:
    if key in NOT_PROSE:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in prose(v, k)]
    if isinstance(value, list):
        return [s for v in value for s in prose(v)]
    return []


def screened_text(content) -> str:
    return " ".join(s for block in blocks_of(content) for s in prose(block))
