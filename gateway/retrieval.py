"""Retrieval with the rights filter on the query — `retrieve_sources`.

The registry says the rights filter runs on the query and is re-checked by
no_permission_leak at NodeChecks. This is the first half: only chunks from
articles that *every* audience of the course may see are offered to the model.
The second half is the Datalog guard, and it is not redundant — a model can
cite a chunk id it was never given.

Scoped to a topic as the specification asks: a lesson is given the chunks about
its own skill, not every chunk its audience may read, or every lesson ends up
teaching the whole course. Rights narrow first, relevance second, so scoping
can never widen what an audience sees.
"""
from __future__ import annotations


def retrieve(world, audiences: list[str], kb_chunks: list[dict], skills=None) -> list[dict]:
    open_to_all = set.intersection(*(set(world.visibility.get(a, [])) for a in audiences)) \
        if audiences else set()
    allowed = {c for art in world.articles if art["id"] in open_to_all for c in art["chunks"]}
    open_chunks = [c for c in kb_chunks if c["id"] in allowed]
    return open_chunks if skills is None else [c for c in open_chunks if c.get("skill") in set(skills)]
