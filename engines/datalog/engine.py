"""Reachability: what reaches what, and through how many hops.

Two questions live here. Does every claim in a node hang on a retrieved chunk,
and is there any source in this course that some member of the intended audience
cannot see. The second is the one the platform cannot answer for us — it asks
"may this person see this article", one viewer at a time, and a course asks the
harder question over a whole audience.

Visibility itself is never derived here. The specification is explicit that the
generator must not re-implement the platform's predicate; it asks and treats the
answer as a fact. So the facts below come from the fixture's resolved answer,
and this engine reasons over them rather than about them.

The refusal is a path — node, source, audience — because "denied" tells an author
nothing and a path tells them which citation to drop.
"""
from __future__ import annotations

from ..contract import EngineUnavailable, Verdict, allowed, refused

ENGINE = "datalog"


def _pydatalog():
    try:
        from pyDatalog import pyDatalog
    except ImportError as exc:                    # noqa: BLE001
        raise EngineUnavailable(f"pyDatalog is not installed: {exc}") from exc
    return pyDatalog


# The rules, as rules. Written as text rather than through the operator API
# because that API injects its terms into the calling module's globals, which
# works at import time and silently does not inside a function — and because a
# relation is easier to review when it looks like one.
RULES = """
leak(N, C, A) <= cites(N, C) & in_audience(A) & ~visible(C, A)
"""


def check_permission_leak(nodes: list[dict], audiences: list[str],
                          resolved_visibility: dict) -> Verdict:
    """Is there a source in this course some member of the audience cannot see?"""
    pd = _pydatalog()
    pd.clear()
    pd.create_terms("cites, visible, in_audience, leak, N, C, A")

    for node in nodes:
        for chunk in node.get("cites") or []:
            pd.assert_fact("cites", node["id"], chunk)
    for name in audiences:
        pd.assert_fact("in_audience", name)
        for chunk in resolved_visibility.get(name) or []:
            pd.assert_fact("visible", chunk, name)

    pd.load(RULES)
    answer = pd.ask("leak(N, C, A)")
    rows = sorted(answer.answers) if answer else []
    paths = [{"node": n, "source": c, "audience": a} for n, c, a in rows]
    if not paths:
        return allowed(engine=ENGINE, checked=len(nodes))
    first = paths[0]
    return refused(
        kind="leak-path",
        summary=(f"{first['node']} cites {first['source']}, which "
                 f"{first['audience']} cannot see"),
        detail=paths,
        engine=ENGINE)


def check_grounding(nodes: list[dict], known_chunks: set[str]) -> Verdict:
    """Does every claim hang on a chunk that exists?"""
    ungrounded = [{"node": n["id"], "source": c}
                  for n in nodes for c in (n.get("cites") or [])
                  if c not in known_chunks]
    if not ungrounded:
        return allowed(engine=ENGINE, checked=len(nodes))
    return refused(
        kind="leak-path",
        summary=f"{ungrounded[0]['node']} cites {ungrounded[0]['source']}, which is not in the knowledge base",
        detail=ungrounded,
        engine=ENGINE)
