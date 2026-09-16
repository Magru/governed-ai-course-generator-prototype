"""The guards the state store answers — bookkeeping, not judgement.

Twenty of the glossary's thirty-eight are this: a counter, a pointer, a flag
written on the way into a state and read on the way out. Each function returns
a bool, because a store fact has no artifact beyond itself; the refusal a person
reads is the fact, and the machine records which literal failed.

Three are owned jointly with a layer this prototype does not have — the
engines/registry.py PARTIAL list says which share is missing. Here each answers
the store's share only, from what the event payload carried, and says so.

A guard that cannot be decided raises Undecidable. It is never False: "we do
not know whether the guardrail passed" read as "it did not" would route to
repair; read as "it did" would admit the work. Either is a lie.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable

from engines.registry import IMPLEMENTED

from .endpoints import LIVE_LINEAGE
from .engine_guards import Context, course_nodes
from .guard_expressions import Literal


class Undecidable(RuntimeError):
    """A guard with no fact to stand on. Stops the step; never a verdict."""


def _obj(lit: Literal, ctx: Context):
    """The object a scoped guard is about: the node when the row is the node
    machine's or the literal says (node), the revision otherwise."""
    if ctx.node is not None and lit.arg != "revision":
        return ctx.node
    return ctx.rev


def _compare(actual, lit: Literal) -> bool:
    if lit.op == "=":
        return actual == lit.value
    if lit.op == "∉":
        return actual not in lit.value
    raise Undecidable(f"{lit.raw}: {lit.name} is compared, and no comparison was written")


def _pending(lit: Literal, ctx: Context):
    op = _obj(lit, ctx).pending_operation
    if op is None:
        raise Undecidable(f"{lit.raw}: no operation is outstanding to ask about")
    return op


def _key_unused(lit: Literal, ctx: Context) -> bool:
    op = _pending(lit, ctx)
    if op.awaited == "GuardrailVerdict":
        # "a screening writes no course state, so there is nothing to
        # reconcile" (node row 7). A screening never landed; counting one that
        # did as landed would read an unanswered screening as an allow.
        return True
    return op.key not in ctx.store.used_keys


def fingerprint(rev) -> str:
    """What a learner would read. Two revisions with the same one are the same
    course, whatever their ids."""
    body = {"outline": [rev.nodes[i].spec for i in rev.committed_outline or [] if i in rev.nodes],
            "nodes": {n.id: n.content for n in rev.nodes.values() if n.state != "Removed"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _versions_current(ctx: Context) -> bool:
    """Every stamp on the revision and on each of its nodes names the version
    in force. A revision is stamped with policy and guardrail when its brief is
    checked; a node with all four when it is approved. An unstamped artifact is
    not current — it was never judged against anything."""
    current = ctx.store.current
    artifacts = [ctx.rev.stamps] + [n.stamps for n in ctx.rev.nodes.values()
                                    if n.state != "Removed"]
    return all(a and all(current[k] == v for k, v in a.items()) for a in artifacts)


def _differs_from_live(lit: Literal, ctx: Context) -> bool:
    live = ctx.store.live_pointer
    if live is None or live == ctx.rev.id:
        return True
    return fingerprint(ctx.rev) != fingerprint(ctx.store.revisions[live])


def _in_outline(lit: Literal, ctx: Context) -> bool:
    # "evaluated against the proposal being committed, never against
    # outline_version, which the very same transition is about to advance."
    proposal = (ctx.payload or {}).get("outline") or ctx.rev.proposal
    if not proposal:
        raise Undecidable(f"{lit.raw}: no outline is being committed")
    return ctx.node.id in {n["id"] for n in proposal["nodes"]}


def _all_visuals_reviewed(lit: Literal, ctx: Context) -> bool:
    needs = {b["id"] for b in ctx.world.catalog["blocks"] if b.get("requires_visual_review")}
    blocks = (ctx.node.content or {}).get("blocks") or []
    queue = {f"{ctx.node.id}.blocks[{i}]" for i, b in enumerate(blocks) if b.get("type") in needs}
    reviewed = set((ctx.payload or {}).get("visuals_reviewed") or ())
    return queue <= reviewed


class ServiceDown(Undecidable):
    """The managed guardrail did not answer. An unknown, which the table routes
    to recovery — never a verdict in either direction."""


def _guardrail_clean(lit: Literal, ctx: Context) -> bool:
    payload = ctx.payload or {}
    if "verdict" in payload:
        return payload["verdict"] == "allow"
    # Inside StaleReview nothing arrives as an event — the table has no
    # GuardrailVerdict row there, only a Timeout one. So the machine asks the
    # screening port itself, once per guardrail version, and an unreachable
    # service is the Timeout row's business.
    current = ctx.store.current["guardrail"]
    last = ctx.rev.screened.get("revision")
    if not last or last["guardrail_version"] != current:
        screener = ctx.machine.screener
        if screener is None:
            raise Undecidable(f"{lit.raw}: no screening port is attached to ask")
        try:
            verdict = screener(ctx.rev, current)
        except ConnectionError as exc:
            raise ServiceDown(f"{lit.raw}: the guardrail did not answer: {exc}") from exc
        last = ctx.rev.screened["revision"] = {"verdict": verdict, "guardrail_version": current}
    return last["verdict"] == "allow"


def _affected(lit: Literal, ctx: Context) -> bool:
    # Two questions wearing one name (glossary). The structural one is the
    # store's: is this revision stamped under the version the change replaces?
    # The meaning one — does the change reach what the revision says — is the
    # managed guardrail's, and arrives on the event as `reaches`, per revision.
    change = ctx.payload or {}
    kind = {"PolicyChanged": "policy", "GuardrailChanged": "guardrail",
            "CatalogChanged": "catalog", "KBUpdated": "kb"}.get(change.get("event", ""))
    to = change.get("to")
    if kind is None or to is None:
        raise Undecidable(f"{lit.raw}: the change does not say what moved")
    if ctx.rev.stamps.get(kind) == to:
        return False
    reaches = change.get("reaches") or {}
    if ctx.rev.id not in reaches:
        raise Undecidable(f"{lit.raw}: nothing judged whether the change reaches revision {ctx.rev.id}")
    return bool(reaches[ctx.rev.id])


def _has_active_readers(lit: Literal, ctx: Context) -> bool:
    readers = ctx.store.readers
    if ctx.rev.id not in readers:
        raise Undecidable(f"{lit.raw}: the store keeps no reader window for revision {ctx.rev.id}")
    return readers[ctx.rev.id] > 0


def _depends_on(lit: Literal, ctx: Context) -> bool:
    edited = (ctx.payload or {}).get("node")
    if edited is None:
        raise Undecidable(f"{lit.raw}: no edited or removed node was named")
    reached = IMPLEMENTED["depends_on(node, edited)"](course_nodes(ctx.rev), edited)
    return ctx.node.id in reached and ctx.node.id != edited


STORE_GUARDS: dict[str, Callable[[Literal, Context], bool]] = {
    "course_state(revision)": lambda lit, ctx: _compare(ctx.rev.state, lit),
    "blocked_at(revision)": lambda lit, ctx: _compare(ctx.rev.blocked_at, lit),
    "recovery_from(node)": lambda lit, ctx: _compare(ctx.node.recovery_from, lit),
    "has_nodes(revision)": lambda lit, ctx: bool(ctx.rev.nodes),
    "has_outline(revision)": lambda lit, ctx: bool(ctx.rev.proposal or ctx.rev.committed_outline),
    "reason_given(action)": lambda lit, ctx: bool((ctx.payload or {}).get("reason")),
    "is_draft_revision(revision)": lambda lit, ctx: not ctx.rev.ever_published,
    "in_live_lineage(revision)": lambda lit, ctx: (
        ctx.rev.ever_published and ctx.rev.state in LIVE_LINEAGE),
    "lost_live_pointer(revision)": lambda lit, ctx: ctx.store.live_pointer not in (None, ctx.rev.id),
    "retry_budget_left(scope)": lambda lit, ctx: _obj(lit, ctx).repair_count < ctx.store.budget(),
    "idempotency_key_unused(operation)": lambda lit, ctx: _key_unused(lit, ctx),
    "hand_edited(node)": lambda lit, ctx: ctx.node.hand_edited,
    "in_outline(node, committed_outline)": _in_outline,
    "all_nodes_approved(revision)": lambda lit, ctx: all(
        n.state == "NodeApproved" for n in ctx.rev.nodes.values() if n.state != "Removed"),
    "no_stale_nodes(revision)": lambda lit, ctx: not (
        ctx.rev.stale_nodes or any(n.state == "NeedsRevalidation" for n in ctx.rev.nodes.values())),
    "versions_current(artifact)": lambda lit, ctx: _versions_current(ctx),
    "differs_from_live(revision)": _differs_from_live,
    "all_visuals_reviewed(node)": _all_visuals_reviewed,
    "notice_approved(recipient_set)": lambda lit, ctx: bool((ctx.payload or {}).get("notice_approved")),
    "guardrail_clean(artifact)": _guardrail_clean,
    "affected(revision)": _affected,
    "has_active_readers(revision)": _has_active_readers,
    "depends_on(node, edited)": _depends_on,
}

#: In the glossary and asked by no row. Kept here so the registry test can hold
#: the glossary to exactly STORE_GUARDS ∪ engine ADAPTERS ∪ this.
NOT_ASKED_BY_A_ROW = {
    "outline_version(revision)":
        "read through committed_outline; the glossary says in_outline must never read it",
}
