"""What the model is asked: the rules for a phase, and the shape to return.

The rules name what the catalog has — its skills, its block types and what each
block must carry — because a model told only "use catalog skills" can only
guess, and every guess is a repair the course pays for. The shape names the
same lists as enums, so a provider that decodes against the schema cannot
produce anything else.

Neither replaces a check. The machine judges every answer against the full
schemas and the catalog's own rows; what is asked here only makes a right
answer likelier on the first attempt.
"""
from __future__ import annotations

import copy

from engines.schema.schemas import OUTLINE

OUTLINE_RULES = ("outline\nPropose modules as topics and exams: titles and learning objectives "
                 "only. Every skill must be one the catalog lists. An exam's topics are the ids "
                 "of the topic nodes in this outline that it tests, and nothing else; a topic "
                 "node has no topics. Return the outline schema.")
# What `topics` means, said where the model reads the field: told nothing, a
# model fills it with learning objectives, which name no node an exam can wait for.
TOPICS = {"type": "array", "items": {"type": "string"},
          "description": "exam only: ids of topic nodes in this same outline"}
NODE_RULES = ("node:{node}\nWrite this node from the sources only. Cite every claim by chunk "
              "id; cite nothing you were not given. Blocks must be catalog block types.")

# Every field a block may carry. A provider that is told nothing about an
# array's items may refuse to fill it.
BLOCK_FIELDS = {"type": {"type": "string"}, "text": {"type": "string"},
                "cites": {"type": "array", "items": {"type": "string"}},
                "src": {"type": "string"}, "alt": {"type": "string"}, "caption": {"type": "string"},
                "items": {"type": "array", "items": {"type": "string"}},
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "answer": {"type": "integer", "minimum": 0, "maximum": 20},
                "points": {"type": "integer", "minimum": 0, "maximum": 100}}
# The bounds on numbers are generous on purpose: they stop a runaway answer —
# a number thousands of digits long — not a lesson longer than the organisation
# allows, which is the arithmetic check's to refuse with the limit it broke.
NODE_SCHEMA = {"type": "object", "required": ["blocks", "cites"],
               "properties": {"blocks": {"type": "array", "items": {"type": "object", "required": ["type"],
                                                                    "properties": BLOCK_FIELDS}},
                              "cites": {"type": "array", "items": {"type": "string"}},
                              "minutes": {"type": "integer", "minimum": 1, "maximum": 600},
                              "points_total": {"type": "integer", "minimum": 0, "maximum": 1000},
                              "questions": {"type": "array", "items": {
                                  "type": "object",
                                  "properties": {"points": {"type": "integer", "minimum": 0, "maximum": 100}}}}}}


def outline_request(world) -> tuple[str, dict]:
    rules = f"{OUTLINE_RULES}\nThe catalog's skills: {', '.join(world.skills)}."
    schema = copy.deepcopy(OUTLINE)
    schema["properties"]["nodes"]["items"]["properties"]["skill"] = {"type": "string", "enum": list(world.skills)}
    schema["properties"]["nodes"]["items"]["properties"]["topics"] = copy.deepcopy(TOPICS)
    return rules, schema


def node_request(world, node_id: str) -> tuple[str, dict]:
    carries = "; ".join(f"{kind} ({', '.join(world.block_schemas[kind].get('required') or [])})"
                        for kind in world.block_types)
    limit = world.thresholds.get("max_minutes_per_lesson")
    rules = (f"{NODE_RULES.format(node=node_id)}\nBlock types, and what each must carry, and nothing "
             f"else: {carries}.\nState the node's minutes{f', at most {limit}' if limit else ''}. "
             f"An exam is made of quiz blocks, and its points_total is the sum of their points.")
    schema = copy.deepcopy(NODE_SCHEMA)
    schema["required"] = [*schema["required"], "minutes"]
    if limit:
        schema["properties"]["minutes"]["maximum"] = limit
    # One shape per block type, each exactly the catalog's row: a block offered
    # every field of every type fills fields its own type refuses.
    schema["properties"]["blocks"]["items"] = {"anyOf": [_block(world, kind) for kind in world.block_types]}
    return rules, schema


def _block(world, kind: str) -> dict:
    row = world.block_schemas[kind]
    return {"type": "object", "required": ["type", *(row.get("required") or [])],
            "properties": {"type": {"type": "string", "enum": [kind]},
                           **{name: BLOCK_FIELDS.get(name, sub)
                              for name, sub in (row.get("properties") or {}).items()},
                           "cites": BLOCK_FIELDS["cites"]}}
