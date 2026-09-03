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

The refusal is a path — node, chunk, article, audience — because "denied" tells
an author nothing and a path tells them which citation to drop and which
document it came out of. Four steps, not three: permissions attach to articles,
and a chunk is a fragment of one. An earlier version went straight from chunk to
audience, which meant the artifact could not say what the author had actually
reached into.
"""
from __future__ import annotations

from ..contract import Verdict, allowed, refused
from .base import ENGINE, answers, pydatalog, rules, session
from .structure import (cascade, check_content_approved,                 # noqa: F401
                        check_ordering_acyclic, check_references_live,
                        check_skills_grounded)


# The rules, as rules. Written as text rather than through the operator API
# because that API injects its terms into the calling module's globals, which
# works at import time and silently does not inside a function — and because a
# relation is easier to review when it looks like one.
RULES = """
leak(N, C, R, A) <= cites(N, C) & in_article(C, R) & in_audience(A) & ~visible(R, A)
ungrounded(N, C) <= cites(N, C) & ~in_kb(C)
"""

TERMS = ("cites, in_article, in_kb, visible, in_audience, "
         "leak, ungrounded, N, C, R, A")
SEED = {"visible": 2, "in_article": 2, "in_kb": 1}


def _load(nodes: list[dict], *, articles: list[dict] | None = None,
          audiences: list[str] | None = None,
          resolved_visibility: dict | None = None) -> object:
    """One place where facts become facts, so no query runs on a half-loaded base."""
    pd = session(TERMS, SEED)
    for node in nodes:
        for chunk in node.get("cites") or []:
            pd.assert_fact("cites", node["id"], chunk)
    for article in articles or []:
        for chunk in article.get("chunks") or []:
            pd.assert_fact("in_article", chunk, article["id"])
            pd.assert_fact("in_kb", chunk)
    for name in audiences or []:
        pd.assert_fact("in_audience", name)
        for article_id in (resolved_visibility or {}).get(name) or []:
            pd.assert_fact("visible", article_id, name)
    return rules(pd, RULES)


def check_permission_leak(nodes: list[dict], articles: list[dict],
                          audiences: list[str],
                          resolved_visibility: dict) -> Verdict:
    """Is there a source in this course some member of the audience cannot see?"""
    pd = _load(nodes, articles=articles, audiences=audiences,
               resolved_visibility=resolved_visibility)
    rows = answers(pd, "leak(N, C, R, A)")
    paths = [{"node": n, "chunk": c, "article": r, "audience": a}
             for n, c, r, a in rows]
    if not paths:
        return allowed(engine=ENGINE, checked=len(nodes))
    first = paths[0]
    return refused(
        kind="leak-path",
        summary=(f"{first['node']} cites {first['chunk']} from "
                 f"{first['article']}, which {first['audience']} cannot see"),
        detail=paths,
        engine=ENGINE)


def check_grounding(nodes: list[dict], articles: list[dict]) -> Verdict:
    """Does every claim hang on a chunk that exists?

    This was a list comprehension wearing the label `engine="datalog"`. It gave
    the right answer and it was not the engine it said it was — and the point of
    naming a layer in a refusal is that a reader can go and read the rule.
    """
    pydatalog()          # so an absent library is EngineUnavailable, not a pass
    pd = _load(nodes, articles=articles)
    rows = answers(pd, "ungrounded(N, C)")
    missing = [{"node": n, "chunk": c} for n, c in rows]
    if not missing:
        return allowed(engine=ENGINE, checked=len(nodes))
    return refused(
        kind="ungrounded-claim",
        summary=(f"{missing[0]['node']} cites {missing[0]['chunk']}, which is "
                 f"not in the knowledge base"),
        detail=missing,
        engine=ENGINE)
