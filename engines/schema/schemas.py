"""The shapes a brief, an outline and a content block must have.

Written here rather than fetched from the platform because the platform's own
schemas describe what it will store, and this asks a narrower question: is what
the model produced the shape the next layer can reason about. A block whose
`points` is the string "four" is storable and not addable.

The block types are the ones `namespace.yaml` declares. That list is the
organisation's, so it is read rather than repeated — a second copy would be the
copy that drifts.
"""
from __future__ import annotations

ID = {"type": "string", "minLength": 1}

BRIEF = {
    "type": "object",
    "required": ["id", "title", "audience", "objectives", "minutes_per_lesson"],
    "additionalProperties": True,
    "properties": {
        "id": ID,
        "title": {"type": "string", "minLength": 1},
        "audience": {"type": "array", "items": ID, "minItems": 1},
        "objectives": {"type": "array", "items": ID, "minItems": 1},
        "minutes_per_lesson": {"type": "integer", "minimum": 1},
        "requested_nodes": {"type": "integer", "minimum": 1},
    },
}

OUTLINE = {
    "type": "object",
    "required": ["nodes"],
    "properties": {
        "nodes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "type"],
                "properties": {
                    "id": ID,
                    "type": {"enum": ["topic", "exam"]},
                    "skill": ID,
                    "topics": {"type": "array", "items": ID},
                },
            },
        },
    },
}


def block(block_types: list[str]) -> dict:
    """A content block, against the organisation's own list of block types."""
    return {
        "type": "object",
        "required": ["type"],
        "properties": {
            "type": {"enum": list(block_types)},
            "text": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
            "points": {"type": "integer", "minimum": 0},
            "options": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        },
    }


SHAPES = {"brief": BRIEF, "outline": OUTLINE}
