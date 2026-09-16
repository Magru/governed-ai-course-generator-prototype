"""What the output guardrail reads from a node: every word a learner will see.

Picking named fields — text, question, caption — left the rest unread, and the
rest is where a refused sentence goes next: a checklist item, a quiz option, an
image's alt text, a title beside the blocks. So the screened text is every
string in the node, except what is not prose: a block's type and citations,
an image's source, which goes to the image screening, and the ids the outline
owns.
"""
from __future__ import annotations

#: Top-level fields of a block that are not prose. `src` only on an image: on
#: any other block it is a string a learner may be shown, and it is read.
BLOCK_IDS = {"type", "cites"}
#: Top-level fields of a node that name things rather than say them.
NODE_IDS = {"id", "cites", "type", "skill", "topics", "requires", "refers_to"}


def blocks_of(content) -> list[dict]:
    blocks = content.get("blocks") if isinstance(content, dict) else None
    return [b for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []


def prose(value) -> list[str]:
    """Every string, at any depth. A key is never prose, and never a way out."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in prose(v)]
    if isinstance(value, list):
        return [s for v in value for s in prose(v)]
    return []


def block_prose(block: dict) -> list[str]:
    skip = BLOCK_IDS | ({"src"} if block.get("type") == "image" else set())
    return [s for k, v in block.items() if k not in skip for s in prose(v)]


def screened_text(content) -> str:
    if not isinstance(content, dict):
        return " ".join(prose(content))
    around = [s for k, v in content.items() if k not in NODE_IDS | {"blocks"} for s in prose(v)]
    return " ".join([s for block in blocks_of(content) for s in block_prose(block)] + around)
