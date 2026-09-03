"""The shape of a course: what it claims, what it points at, what it waits on.

Five guards live here, and they are all the same kind of question — does this
thing the course asserts actually reach something that exists and is allowed.
`sources.py` asks it of retrieved material; this asks it of the skeleton.

Every one of them refuses with the thing `transitions.html` §4 says it must: the
invented skills, the dead reference, the cycle, the outstanding topics.
"""
from __future__ import annotations

from ..contract import Verdict, allowed, refused
from .base import ENGINE, answers, rules, session

TERMS = ("node_teaches, catalog_skill, refers_to, in_outline, prerequisite, "
         "position, exam_topic, approved, reaches, cycle, out_of_order, "
         "invented_skill, dead_reference, outstanding, depends, "
         "N, T, S, A, B, X, E, PA, PB")

RULES = """
invented_skill(N, S) <= node_teaches(N, S) & ~catalog_skill(S)
dead_reference(N, T) <= refers_to(N, T) & ~in_outline(T)
reaches(A, B) <= prerequisite(A, B)
reaches(A, B) <= reaches(A, X) & prerequisite(X, B)
cycle(A) <= reaches(A, A)
out_of_order(A, B) <= prerequisite(A, B) & position(A, PA) & position(B, PB) & (PA < PB)
outstanding(E, T) <= exam_topic(E, T) & in_outline(T) & ~approved(T)
depends(A, B) <= prerequisite(A, B)
depends(A, B) <= depends(A, X) & prerequisite(X, B)
"""

SEED = {"catalog_skill": 1, "in_outline": 1, "approved": 1, "prerequisite": 2}


def _base(*, nodes=(), catalog_skills=(), outline=(), approved_nodes=()):
    pd = session(TERMS, SEED)
    for skill in catalog_skills:
        pd.assert_fact("catalog_skill", skill)
    for node_id in outline:
        pd.assert_fact("in_outline", node_id)
    for node_id in approved_nodes:
        pd.assert_fact("approved", node_id)
    for position, node in enumerate(nodes):
        pd.assert_fact("position", node["id"], position)
        if node.get("skill"):
            pd.assert_fact("node_teaches", node["id"], node["skill"])
        for target in node.get("refers_to") or []:
            pd.assert_fact("refers_to", node["id"], target)
        for required in node.get("requires") or []:
            pd.assert_fact("prerequisite", node["id"], required)
        for topic in node.get("topics") or []:
            pd.assert_fact("exam_topic", node["id"], topic)
    return rules(pd, RULES)


def check_skills_grounded(nodes: list[dict], catalog_skills: list[str]) -> Verdict:
    """Does every skill the outline claims exist in the catalog?"""
    pd = _base(nodes=nodes, catalog_skills=catalog_skills)
    invented = [{"node": n, "skill": s} for n, s in answers(pd, "invented_skill(N, S)")]
    if not invented:
        return allowed(engine=ENGINE, checked=len(nodes))
    return refused(
        kind="invented-skill",
        summary=("the outline teaches skills the catalog does not have: "
                 + ", ".join(sorted({row["skill"] for row in invented}))),
        detail=invented,
        engine=ENGINE)


def check_references_live(nodes: list[dict], outline: list[str],
                          outline_version: str) -> Verdict:
    """Does every cross-reference still point at a node the skeleton has?

    The outline version is in the refusal because that is what changed: the
    reference was live when it was written, and an outline commit dropped its
    target. An author told only "dead reference" goes looking for a typo.
    """
    pd = _base(nodes=nodes, outline=outline)
    dead = [{"node": n, "target": t, "outline_version": outline_version}
            for n, t in answers(pd, "dead_reference(N, T)")]
    if not dead:
        return allowed(engine=ENGINE, checked=len(nodes))
    first = dead[0]
    return refused(
        kind="dead-reference",
        summary=(f"{first['node']} points at {first['target']}, which outline "
                 f"{outline_version} no longer contains"),
        detail=dead,
        engine=ENGINE)


def check_ordering_acyclic(nodes: list[dict]) -> Verdict:
    """Has the prerequisite graph a cycle, and does it agree with lesson order?

    Two failures, one guard, because both make the course unteachable and the
    glossary states them together. They are reported apart: a cycle has no
    resolution but an edit, and an order disagreement is fixed by moving a
    lesson.
    """
    pd = _base(nodes=nodes)
    cycles = sorted({a for (a,) in answers(pd, "cycle(A)")})
    misordered = [{"node": a, "requires": b}
                  for a, b in answers(pd, "out_of_order(A, B)")]
    if not cycles and not misordered:
        return allowed(engine=ENGINE, checked=len(nodes))
    if cycles:
        return refused(
            kind="prerequisite-cycle",
            summary="these nodes require each other: " + ", ".join(cycles),
            detail={"cycle": cycles, "out_of_order": misordered},
            engine=ENGINE)
    first = misordered[0]
    return refused(
        kind="ordering-conflict",
        summary=(f"{first['node']} comes before {first['requires']} and "
                 f"requires it"),
        detail={"cycle": [], "out_of_order": misordered},
        engine=ENGINE)


def check_content_approved(nodes: list[dict], outline: list[str],
                           approved_nodes: list[str]) -> Verdict:
    """May this exam be generated — is every topic it tests approved?

    Quantified over the topics still in the committed outline. A topic dropped
    from the skeleton stops being a precondition, rather than becoming one that
    can never be met and holding the exam forever.
    """
    pd = _base(nodes=nodes, outline=outline, approved_nodes=approved_nodes)
    rows = [{"exam": e, "topic": t} for e, t in answers(pd, "outstanding(E, T)")]
    if not rows:
        return allowed(engine=ENGINE, checked=len(nodes))
    return refused(
        kind="outstanding-topics",
        summary=("the exam tests material nobody has approved: "
                 + ", ".join(sorted({r["topic"] for r in rows}))),
        detail=rows,
        engine=ENGINE)


def cascade(nodes: list[dict], edited: str) -> list[str]:
    """Which nodes depend on the one that was edited, directly or through others.

    Not a guard and not a refusal — a derivation. It is what the staleness
    cascade reads to decide which stamps to break, so it returns the set rather
    than a verdict, and the caller decides what that costs.
    """
    pd = _base(nodes=nodes)
    return sorted({a for a, b in answers(pd, "depends(A, B)") if b == edited})
