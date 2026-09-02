"""Did this run obey every property the architecture promises?

The only layer that reads the past rather than the present. It refuses with the
violated formula and the event that broke it, because "the trace is invalid" is
not something a person can act on and "step 14, NodeEdited, revision 1 was
edited after publication" is.

Three things can go wrong with a run and they are not the same thing:

  the shape is wrong   — the run carries a field nobody declared, or a state
                         name that is not in the inventory. Nothing is checked;
                         deciding properties about a malformed run produces
                         confident nonsense.
  a property is broken — the run did what the model forbids.
  a fact is missing    — the run does not carry what a property would need. It
                         refuses like the others, because absence of a verdict
                         is never a permissive verdict, but it names a gap in
                         the recorder rather than a fault in the run.
"""
from __future__ import annotations
import pathlib

from ..contract import EngineUnavailable, Verdict, allowed, refused
from .invariants import REGISTRY
from .trace import Unrecorded, build

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


def check(raw: list[dict]) -> Verdict:
    trace, problems = build(raw)
    if problems:
        return refused(
            kind="malformed-trace",
            summary=f"the run does not match model/trace-schema.yaml: {problems[0]}",
            detail=[{"problem": p} for p in problems],
            engine=ENGINE)

    violations = []
    for ident in sorted(REGISTRY, key=lambda x: int(x[1:])):
        formula, fn = REGISTRY[ident]
        try:
            found = fn(trace)
        except Unrecorded as gap:
            violations.append({"invariant": ident, "formula": formula,
                               "step": gap.step, "event": trace[gap.step].event,
                               "kind": "unrecorded", "why": str(gap)})
            continue
        for v in found:
            violations.append({"invariant": ident, "formula": v.formula,
                               "step": v.step, "event": v.event,
                               "kind": v.kind, "why": v.why})

    if not violations:
        return allowed(engine=ENGINE, steps=len(trace), invariants=len(REGISTRY))
    first = violations[0]
    return refused(
        kind="violated-formula",
        summary=f"{first['invariant']} {first['kind']} at step {first['step']} "
                f"({first['event']}): {first['why']}",
        detail=violations,
        engine=ENGINE)
