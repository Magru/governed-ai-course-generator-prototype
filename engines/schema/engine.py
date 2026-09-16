"""Does this artifact have the shape the next layer can reason about?

Step one of the membrane, and the layer that was missing. Everything downstream
assumes it ran: Z3 reads `minutes_per_lesson` as a number, Datalog reads a
node's `topics` as a list of ids. Without this, a model that returns a string
where an integer belongs reaches an engine that will either crash or, worse,
coerce it and answer confidently about the coercion.

The refusal is the failing path and the expected type, because "the brief is
invalid" sends an author to read the whole thing and `brief.audience[1]: expected
a string, got 4` sends them to one character.
"""
from __future__ import annotations

from ..contract import EngineUnavailable, Verdict, allowed, refused
from .schemas import SHAPES, block

ENGINE = "schema"


def _validator():
    try:
        import jsonschema
    except ImportError as exc:                    # noqa: BLE001
        raise EngineUnavailable(f"jsonschema is not installed: {exc}") from exc
    return jsonschema


def _path(error) -> str:
    """`brief.audience[1]` rather than `deque(['audience', 1])`."""
    out = ""
    for part in error.absolute_path:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out.lstrip(".") or "(the whole artifact)"


def _expected(error) -> str:
    """The rule that failed, as the schema states it. Reading the first keyword
    present instead reported `type: string` for a string that was too short, and
    that wrong reason went into the repair prompt."""
    schema = error.schema if isinstance(error.schema, dict) else {}
    if error.validator in schema:
        return f"{error.validator}: {schema[error.validator]}"
    return error.validator or "a different shape"


def check_blocks(node: dict, block_types: list[str], block_schemas: dict | None = None) -> Verdict:
    """Does every content block in this node have a shape the catalog defines?

    A separate guard from `schema_valid`, with a separate owner: the catalog
    decides what a block may be, and this validates against the list the
    organisation publishes rather than one written here. Kept apart because the
    glossary keeps them apart, and a package that answers a question the guard
    registry does not list is a map with a road missing from it.
    """
    blocks = node.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        # A node with no blocks has no shape to be wrong about, so the loop
        # below would pass it — and an empty answer from the model would
        # travel through every later check and be published as a lesson.
        return refused(
            kind="failing-path",
            summary=f"{node.get('id')}.blocks: expected at least one content block",
            detail=[{"path": f"{node.get('id')}.blocks", "expected": "minItems: 1",
                     "found": repr(blocks)}],
            engine=ENGINE)
    failures = []
    for index, one in enumerate(blocks):
        verdict = check(one, "block", block_types=block_types)
        if verdict.ok and block_schemas is not None:
            # The type says which block it is; the catalog's own row says what
            # that block must carry. Checking the type alone passed a paragraph
            # with no text — a lesson made of empty blocks.
            verdict = _against(one, closed(block_schemas[one["type"]]), "block")
            if verdict.ok and one["type"] == "quiz" and not (
                    isinstance(one.get("answer"), int) and 0 <= one["answer"] < len(one["options"])):
                # A schema cannot say "an index into the list beside it".
                expected = (f"an index below {len(one['options'])}"
                            if isinstance(one.get("answer"), int) else "an integer index")
                verdict = refused(kind="failing-path", summary=f"block.answer: expected {expected}",
                                  detail=[{"path": "block.answer", "found": one.get("answer"),
                                           "expected": expected}],
                                  engine=ENGINE)
        if not verdict.ok:
            for failure in verdict.refusal.detail if isinstance(
                    verdict.refusal.detail, list) else []:
                failures.append({**failure,
                                 "path": f"{node.get('id')}.blocks[{index}]"
                                         f".{failure['path'].removeprefix('block.')}"})
    if not failures:
        return allowed(engine=ENGINE, node=node.get("id"),
                       blocks=len(node.get("blocks") or []))
    return refused(
        kind="failing-path",
        summary=f"{failures[0]['path']}: expected {failures[0]['expected']}",
        detail=failures,
        engine=ENGINE)


def closed(schema: dict) -> dict:
    """A block carries what its catalog row defines, its type and its citations
    — nothing else. An open schema let a field no renderer names ride along in
    published content, and what the catalog does not name, nobody screens."""
    return {**schema, "additionalProperties": False,
            "properties": {"type": {}, "cites": {}, **schema.get("properties", {})}}


def check(artifact: dict, shape: str, *, block_types: list[str] | None = None) -> Verdict:
    """Validate one artifact against one named shape.

    `shape` is "brief", "outline" or "block". A block is validated against the
    organisation's own list of block types, which is why that list is passed in
    rather than written here.
    """
    if shape == "block":
        if block_types is None:
            # The organisation decides which blocks exist. Falling back to a
            # list written here would validate against a second opinion.
            return refused(
                kind="unstated-requirement",
                summary="no block types were supplied, so a block cannot be checked",
                detail={"shape": shape},
                engine=ENGINE)
        schema = block(block_types)
    elif shape in SHAPES:
        schema = SHAPES[shape]
    else:
        raise EngineUnavailable(f"no schema is defined for {shape!r}")

    return _against(artifact, schema, shape)


def _against(artifact, schema: dict, shape: str) -> Verdict:
    """One validation, and its refusal as the failing path."""
    errors = sorted(_validator().Draft202012Validator(schema).iter_errors(artifact),
                    key=lambda e: list(e.absolute_path))
    if not errors:
        return allowed(engine=ENGINE, shape=shape)
    failures = [{"path": f"{shape}.{_path(e)}", "expected": _expected(e),
                 "message": e.message} for e in errors]
    first = failures[0]
    return refused(
        kind="failing-path",
        summary=f"{first['path']}: expected {first['expected']}",
        detail=failures,
        engine=ENGINE)
