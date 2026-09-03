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


def check_arithmetic(node: dict, thresholds: dict) -> Verdict:
    """Do the numbers inside a node add up?

    §4: "exam points reach the stated maximum, durations match the block count".
    Two sums, and z3 rather than Python because the refusal has to be the
    failing sum rather than a boolean — an author told "the arithmetic is wrong"
    about a twelve-question exam is being told to go and add it up themselves.

    Both sums are optional in the sense that a node may have neither. Neither is
    optional once the node states one side of it: a node with questions and no
    stated maximum, or blocks and no stated duration, is refused for saying half
    of something rather than passed for saying nothing.
    """
    try:
        import z3
    except ImportError as exc:                    # noqa: BLE001
        raise EngineUnavailable(f"z3 is not installed: {exc}") from exc

    questions = node.get("questions")
    blocks = node.get("blocks")
    stated_total = node.get("points_total")
    stated_minutes = node.get("minutes")

    half_said = []
    if questions is not None and stated_total is None:
        half_said.append("the exam lists questions and states no total")
    if stated_total is not None and questions is None:
        half_said.append("the exam states a total and lists no questions")
    if blocks is not None and stated_minutes is None:
        half_said.append("the node has blocks and states no duration")
    if half_said:
        return refused(kind="unstated-requirement",
                       summary=f"{node.get('id')}: " + "; ".join(half_said),
                       detail={"node": node.get("id"), "incomplete": half_said},
                       engine=ENGINE)

    solver = z3.Solver()
    solver.set(unsat_core=True)
    tracked = {}

    if questions is not None:
        total = z3.Int("points_total")
        tracked["points_total_is_as_stated"] = total == int(stated_total)
        tracked["points_sum_to_the_total"] = total == sum(
            int(q.get("points", 0)) for q in questions)
        tracked["an_exam_is_worth_something"] = total > 0

    if blocks is not None:
        minutes = z3.Int("minutes")
        per_block = int(thresholds.get("minutes_per_block") or 0)
        tracked["duration_is_as_stated"] = minutes == int(stated_minutes)
        if per_block:
            tracked["duration_matches_the_block_count"] = (
                minutes == per_block * len(blocks))
        tracked["a_node_takes_time"] = minutes > 0

    if not tracked:
        return allowed(engine=ENGINE, node=node.get("id"), sums=0)

    for name, claim in tracked.items():
        solver.assert_and_track(claim, z3.Bool(name))

    if solver.check() == z3.sat:
        return allowed(engine=ENGINE, node=node.get("id"), sums=len(tracked))
    core = sorted(str(c) for c in solver.unsat_core())
    return refused(
        kind="failing-sum",
        summary=f"{node.get('id')}: " + ", ".join(core),
        detail={"node": node.get("id"), "core": core},
        engine=ENGINE)
