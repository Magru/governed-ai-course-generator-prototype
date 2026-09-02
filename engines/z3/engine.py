"""Is this brief satisfiable at all — and if not, which requirements collide.

Z3 runs before a single token is generated, which is the whole reason it is
here: a brief that cannot be satisfied costs nothing to refuse and twelve
seconds a node to discover the hard way.

The refusal is an unsat core, not a boolean. That means every assertion has to
be *tracked*: an untracked assertion can make the problem unsatisfiable and then
fail to appear in the explanation, which is worse than no explanation because it
sends the author to fix the wrong requirement. The reference implementation this
project started from used plain `add()` and could not produce a core at all.
"""
from __future__ import annotations

from ..contract import EngineUnavailable, Verdict, allowed, refused

ENGINE = "z3"


def check(brief: dict, thresholds: dict) -> Verdict:
    try:
        import z3
    except ImportError as exc:                    # noqa: BLE001
        raise EngineUnavailable(f"z3 is not installed: {exc}") from exc

    solver = z3.Solver()
    solver.set(unsat_core=True)

    nodes = z3.Int("requested_nodes")
    minutes = z3.Int("minutes_per_lesson")
    breadth = z3.Int("audience_breadth")

    requested = int(brief.get("requested_nodes") or len(brief.get("objectives") or []) or 1)
    asked_minutes = int(brief.get("minutes_per_lesson") or 0)
    asked_breadth = len(brief.get("audience") or [])

    # Every assertion is tracked, and the name is what the author will read back.
    tracked = {
        "requested_nodes": nodes == requested,
        "minutes_per_lesson": minutes == asked_minutes,
        "audience_breadth": breadth == asked_breadth,
        "max_nodes_per_course": nodes <= int(thresholds["max_nodes_per_course"]),
        "max_minutes_per_lesson": minutes <= int(thresholds["max_minutes_per_lesson"]),
        "max_audience_breadth": breadth <= int(thresholds["max_audience_breadth"]),
        "a_lesson_has_positive_length": minutes > 0,
        "a_course_has_at_least_one_node": nodes > 0,
    }
    for name, claim in tracked.items():
        solver.assert_and_track(claim, z3.Bool(name))

    result = solver.check()
    if result == z3.sat:
        model = solver.model()
        return allowed(engine=ENGINE,
                       nodes=model[nodes].as_long(),
                       minutes=model[minutes].as_long())
    if result != z3.unsat:
        raise EngineUnavailable(f"z3 returned {result}, which is neither sat nor unsat")

    core = sorted(str(c) for c in solver.unsat_core())
    return refused(
        kind="unsat-core",
        summary="these requirements cannot hold together: " + ", ".join(core),
        detail=core,
        engine=ENGINE)
