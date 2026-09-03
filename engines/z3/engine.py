"""Is this brief satisfiable at all — and if not, which requirements collide.

Z3 runs before a single token is generated, which is the whole reason it is
here: a brief that cannot be satisfied costs nothing to refuse and twelve
seconds a node to discover the hard way.

The refusal is an unsat core, not a boolean. That means every assertion has to
be *tracked*: an untracked assertion can make the problem unsatisfiable and then
fail to appear in the explanation, which is worse than no explanation because it
sends the author to fix the wrong requirement. The reference implementation this
project started from used plain `add()` and could not produce a core at all.

Nothing here fills in a number the brief did not state. An earlier version read
`requested_nodes` with `int(brief.get(...) or len(objectives) or 1)`, so a brief
that listed three nodes and no count was checked as a two-node brief — the layer
answered confidently about a brief nobody submitted. Absence is a refusal that
names the gap, and where the brief says the same thing twice the disagreement is
handed to z3 rather than resolved by picking one.
"""
from __future__ import annotations

from ..contract import EngineUnavailable, Verdict, allowed, refused

ENGINE = "z3"


def check(brief: dict, thresholds: dict) -> Verdict:
    try:
        import z3
    except ImportError as exc:                    # noqa: BLE001
        raise EngineUnavailable(f"z3 is not installed: {exc}") from exc

    stated_count = brief.get("requested_nodes")          # `is None`, never falsy:
    listed_nodes = brief.get("nodes")                    # 0 is an answer, not a gap
    stated_minutes = brief.get("minutes_per_lesson")
    audience = brief.get("audience")

    unstated = []
    if stated_count is None and listed_nodes is None:
        unstated.append("how many nodes the course should have")
    if stated_minutes is None:
        unstated.append("how long a lesson runs")
    if audience is None:
        unstated.append("who the course is for")
    absent_limits = [k for k in ("max_nodes_per_course", "max_minutes_per_lesson",
                                 "max_audience_breadth") if thresholds.get(k) is None]
    if unstated or absent_limits:
        # Nothing is checked. Satisfiability of a brief with a number invented
        # for it is a fact about the invention.
        return refused(
            kind="unstated-requirement",
            summary="this brief cannot be judged: " + "; ".join(
                unstated + [f"the organisation sets no {k}" for k in absent_limits]),
            detail={"brief_does_not_state": unstated, "no_limit_set": absent_limits},
            engine=ENGINE)

    solver = z3.Solver()
    solver.set(unsat_core=True)

    nodes = z3.Int("requested_nodes")
    minutes = z3.Int("minutes_per_lesson")
    breadth = z3.Int("audience_breadth")

    # Every assertion is tracked, and the name is what the author will read back.
    tracked = {
        "minutes_per_lesson": minutes == int(stated_minutes),
        "audience_breadth": breadth == len(audience),
        "max_nodes_per_course": nodes <= int(thresholds["max_nodes_per_course"]),
        "max_minutes_per_lesson": minutes <= int(thresholds["max_minutes_per_lesson"]),
        "max_audience_breadth": breadth <= int(thresholds["max_audience_breadth"]),
        "a_lesson_has_positive_length": minutes > 0,
        "a_course_has_at_least_one_node": nodes > 0,
    }
    # A brief may say how many nodes it wants and then list them. Both are
    # asserted; if they disagree, z3 names both and the author sees which two
    # statements collide, instead of this function silently preferring one.
    if stated_count is not None:
        tracked["requested_nodes"] = nodes == int(stated_count)
    if listed_nodes is not None:
        tracked["nodes_the_brief_lists"] = nodes == len(listed_nodes)
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
