"""Retrieval with the rights filter on the query — `retrieve_sources`.

The registry says the rights filter runs on the query and is re-checked by
no_permission_leak at NodeChecks. This is the first half: only chunks from
articles that *every* audience of the course may see are offered to the model.
The second half is the Datalog guard, and it is not redundant — a model can
cite a chunk id it was never given.
"""
from __future__ import annotations


def retrieve(world, audiences: list[str], kb_chunks: list[dict]) -> list[dict]:
    open_to_all = set.intersection(*(set(world.visibility.get(a, [])) for a in audiences)) \
        if audiences else set()
    allowed = {c for art in world.articles if art["id"] in open_to_all for c in art["chunks"]}
    return [c for c in kb_chunks if c["id"] in allowed]
