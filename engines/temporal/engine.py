"""Did this run obey every property the architecture promises?

The only layer that reads the past rather than the present. It refuses with the
violated formula and the event that broke it, because "the trace is invalid" is
not something a person can act on and "step 14, NodeEdited, revision 1 was
edited after publication" is.
"""
from __future__ import annotations
import pathlib

from ..contract import EngineUnavailable, Verdict, allowed, refused
from .invariants import REGISTRY

ENGINE = "temporal"
MODEL = pathlib.Path(__file__).resolve().parents[2] / "model" / "invariants.yaml"


def declared() -> dict[str, str]:
    """The formulas as the specification states them."""
    import yaml
    try:
        data = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    except OSError as exc:                        # noqa: BLE001
        raise EngineUnavailable(f"the invariants are not vendored: {exc}") from exc
    return {row["id"]: row["formula"] for row in data["invariants"]}


def check(trace: list[dict]) -> Verdict:
    violations = []
    for ident in sorted(REGISTRY, key=lambda x: int(x[1:])):
        formula, fn = REGISTRY[ident]
        for v in fn(trace):
            violations.append({"invariant": ident, "formula": v.formula,
                               "step": v.step, "event": v.event, "why": v.why})
    if not violations:
        return allowed(engine=ENGINE, steps=len(trace), invariants=len(REGISTRY))
    first = violations[0]
    return refused(
        kind="violated-formula",
        summary=f"{first['invariant']} broken at step {first['step']} "
                f"({first['event']}): {first['why']}",
        detail=violations,
        engine=ENGINE)
