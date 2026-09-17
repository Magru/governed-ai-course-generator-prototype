"""The fifteen guards a formal engine answers, wired to the machine.

Which function answers which guard is `engines/registry.py`'s question and is
not restated here: every adapter looks its engine up by the glossary name. What
this module adds is only the argument — which brief, which nodes, which
audience — picked out of the store and the world. An adapter that computed
anything itself would be a second, quieter engine.

Each adapter returns the engine's Verdict unchanged, so a refusal reaches the
CheckFailed event, the repair prompt and the audit with the artifact the engine
produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from engines.contract import Verdict, refused
from engines.registry import IMPLEMENTED

from .guard_expressions import Literal


@dataclass
class Context:
    """Everything a guard may read at one transition."""
    machine: Any
    rev: Any
    node: Any = None
    payload: dict | None = None

    @property
    def store(self):
        return self.machine.store

    @property
    def world(self):
        return self.machine.world


#: Fields only the committed outline may set.
OUTLINE_OWNED = {"type", "skill", "topics", "requires"}


def engine_node(node) -> dict:
    """A node as every engine takes it: the outline's entry, its generated
    content, and where it stands."""
    # The outline's entry wins: a model that writes `skill` or `topics` into its
    # answer does not get to change what the node was approved to teach.
    # Structure is the outline's even where the outline is silent: a topic's
    # answer that adds `requires` or `topics` would redraw the dependency graph
    # the cascade and the ordering checks read, without an outline commit.
    content = {k: v for k, v in (node.content if isinstance(node.content, dict) else {}).items()
               if k not in OUTLINE_OWNED}
    return {**content, **node.spec, "id": node.id, "state": node.state}


def course_nodes(rev) -> list[dict]:
    return [engine_node(n) for n in rev.nodes.values() if n.state != "Removed"]


def _brief_input(rev) -> dict:
    brief = rev.brief or {}
    return {**brief, "node_count": len(brief.get("nodes") or [])}


def _outline(rev) -> dict:
    return rev.proposal or {}


_ACTION_BY_ARG = {"author, audience": "submit_brief", "structure": "generate_outline",
                  "content": "generate_node", "generate, node": "generate_node"}
_ACTION_BY_STATE = {"BriefValidation": "submit_brief", "OutlineChecks": "generate_outline",
                    "StaleReview": "submit_brief"}


def _policy(lit: Literal, ctx: Context) -> Verdict:
    action = _ACTION_BY_ARG.get(lit.arg or "") or (
        "generate_node" if ctx.node is not None else _ACTION_BY_STATE[ctx.rev.state])
    actor_id = (ctx.payload or {}).get("actor") or ctx.rev.author or ctx.store.config["author"]
    person = ctx.world.people.get(actor_id)
    if person is None:
        return refused("named-rule", f"{actor_id} is not a person in this organisation",
                       {"actor": actor_id}, "opa")
    return IMPLEMENTED["policy_allows(action, role, state)"](
        action, {"id": actor_id, "role": person["role"]}, _brief_input(ctx.rev),
        ctx.rev.state, ctx.world.policy_data)


def _schema(lit: Literal, ctx: Context) -> Verdict:
    shape = lit.arg or ("brief" if ctx.rev.state == "BriefValidation" else "outline")
    artifact = ctx.rev.brief if shape == "brief" else _outline(ctx.rev)
    return IMPLEMENTED["schema_valid(artifact)"](artifact or {}, shape)


def _nodes_in_scope(ctx: Context) -> list[dict]:
    return [engine_node(ctx.node)] if ctx.node is not None else course_nodes(ctx.rev)


def _coverage(lit: Literal, ctx: Context) -> Verdict:
    brief_objectives = (ctx.rev.brief or {}).get("objectives") or []
    develops = ctx.world.develops
    if ctx.node is None:
        return IMPLEMENTED["objectives_covered(scope)"](
            f"rev-{ctx.rev.id}", brief_objectives, _nodes_in_scope(ctx), develops, scope="course")
    skill = ctx.node.spec.get("skill")
    if skill is None:
        # An exam closes no objective of its own; its question is whether its
        # topics are approved, which content_approved asks.
        return IMPLEMENTED["objectives_covered(scope)"](
            f"rev-{ctx.rev.id}", [], _nodes_in_scope(ctx), develops, scope="node")
    # The node's own objective is the one its skill closes — and it must be an
    # objective the brief asked for. Only the brief's objectives are developed
    # here, so a topic teaching something off-brief is refused, not passed.
    in_brief = {s: [o for o in objs if o in brief_objectives] for s, objs in develops.items()}
    return IMPLEMENTED["objectives_covered(scope)"](
        f"rev-{ctx.rev.id}", [skill], _nodes_in_scope(ctx), in_brief, scope="node")


def _every_node(ctx: Context, check) -> Verdict:
    """A node guard asked of a whole revision — re-verification after a catalog
    change — holds when it holds for every node, and refuses with the first."""
    if ctx.node is not None:
        return check(engine_node(ctx.node))
    verdicts = [check(node) for node in course_nodes(ctx.rev)]
    return next((v for v in verdicts if not v.ok), verdicts[0] if verdicts else check({"blocks": None}))


ADAPTERS: dict[str, Callable[[Literal, Context], Verdict]] = {
    "schema_valid(artifact)": _schema,
    "policy_allows(action, role, state)": _policy,
    "feasible(brief)": lambda lit, ctx: IMPLEMENTED["feasible(brief)"](
        ctx.rev.brief or {}, ctx.world.thresholds),
    "skills_grounded(outline)": lambda lit, ctx: IMPLEMENTED["skills_grounded(outline)"](
        _outline(ctx.rev).get("nodes") or [], ctx.world.skills),
    "grounded(node)": lambda lit, ctx: IMPLEMENTED["grounded(node)"](
        _nodes_in_scope(ctx), ctx.world.articles),
    "references_live(node)": lambda lit, ctx: IMPLEMENTED["references_live(node)"](
        _nodes_in_scope(ctx), ctx.rev.committed_outline or [], ctx.rev.outline_version),
    "no_permission_leak(scope)": lambda lit, ctx: IMPLEMENTED["no_permission_leak(scope)"](
        _nodes_in_scope(ctx), ctx.world.articles,
        (ctx.rev.brief or {}).get("audience") or [], ctx.world.visibility),
    "ordering_acyclic(course)": lambda lit, ctx: IMPLEMENTED["ordering_acyclic(course)"](
        course_nodes(ctx.rev)),
    "objectives_covered(scope)": _coverage,
    "content_approved(topics(exam))": lambda lit, ctx: IMPLEMENTED["content_approved(topics(exam))"](
        [engine_node(ctx.node)], ctx.rev.committed_outline or [],
        sorted(n.id for n in ctx.rev.nodes.values() if n.state == "NodeApproved")),
    "trace_satisfies_ltl(course)": lambda lit, ctx: IMPLEMENTED["trace_satisfies_ltl(course)"](
        ctx.machine.trace()),
    "block_schemas_valid(node)": lambda lit, ctx: _every_node(
        ctx, lambda node: IMPLEMENTED["block_schemas_valid(node)"](
            node, ctx.world.block_types, ctx.world.block_schemas)),
    "arithmetic_consistent(node)": lambda lit, ctx: IMPLEMENTED["arithmetic_consistent(node)"](
        engine_node(ctx.node), ctx.world.thresholds),
    "approval_chain_satisfied(revision)": lambda lit, ctx: IMPLEMENTED["approval_chain_satisfied(revision)"](
        ctx.rev.id, [a for a in ctx.rev.approvals
                     if a.get("scope") == ("notice" if ctx.rev.state == "Published" else "publication")],
        ctx.world.policy_data),
}
# depends_on is the fifteenth. It answers with a path rather than a verdict and
# is read by the cascade, not at a transition; the store adapter calls it.
