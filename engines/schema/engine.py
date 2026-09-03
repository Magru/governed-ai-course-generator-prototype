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
    schema = error.schema if isinstance(error.schema, dict) else {}
    for keyword in ("type", "enum", "minimum", "minItems", "minLength"):
        if keyword in schema:
            return f"{keyword}: {schema[keyword]}"
    return error.validator or "a different shape"


def check(artifact: dict, shape: str, *, block_types: list[str] | None = None) -> Verdict:
    """Validate one artifact against one named shape.

    `shape` is "brief", "outline" or "block". A block is validated against the
    organisation's own list of block types, which is why that list is passed in
    rather than written here.
    """
    jsonschema = _validator()
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

    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(artifact),
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
