"""What the machine remembers, and the trace it hands the temporal engine.

The records below are `state-inventory.yaml` made concrete. The trace is
`trace-schema.yaml` made concrete. The two vocabularies were written for
different readers and do not share names — `repair_count` becomes
`retry_budget_left`, `revision.state` becomes `course_state` and
`revision_states` — so `snapshot()` is the one place that translates, and a
test holds it to every field the schema declares. A second translation
anywhere else would be the second copy that drifts.

`approvals[]` is the one variable with no recovery path. Nothing here pretends
to rebuild it from the log: it is appended when an approval happens and read
back as it was written.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Inventory variable → the trace field that carries it, or why none does.
#: Held to both files by a test.
INVENTORY_TO_TRACE = {
    "revision.state": ["course_state", "revision_states"],
    "node.state": ["node_states", "approved_nodes"],
    "revision": ["revision"],
    "forked_from": ["forked_from"],
    "live_pointer": ["live_pointer"],
    "committed_outline": ["committed_outline"],
    "repair_count": ["retry_budget_left"],
    "policy_version": ["policy_version", "current_policy_version"],
    "guardrail_version": ["guardrail_version", "current_guardrail_version"],
    "outline_version": "read by guards through committed_outline, never by an invariant",
    "blocked_at": "routing for the way out of BlockedRecoverable; no invariant reads it",
    "recovery_from": "routing for the way out of NodeRecovery; no invariant reads it",
    "approvals[]": "read by approval_chain_satisfied; the trace records the ApprovalGranted event",
    "idempotency_key": "carried in the envelope of every side-effecting step",
    "trace_id": "carried in the envelope as correlation_id",
    "catalog_version": "stamped with the others; staleness reaches the trace as stale_nodes",
    "kb_snapshot": "stamped with the others; staleness reaches the trace as stale_nodes",
    "model_id + model_version": "provenance on the generated artifact, not a state",
    "threshold_set": "configuration the budgets are read from",
}
#: Trace fields that are derived facts rather than inventory variables.
DERIVED_TRACE_FIELDS = {"permission_checked", "used_restricted", "stale_nodes",
                        "affected", "re_verified"}


@dataclass
class Operation:
    """A side-effecting call whose answer has not arrived."""
    key: str
    issued_from: str
    awaited: str              # the event that would have answered it
    payload: dict = field(default_factory=dict)


@dataclass
class NodeRecord:
    id: str
    spec: dict                          # the outline's entry: type, skill, topics
    state: str = "Planned"
    content: dict | None = None         # blocks and citations, once generated
    recovery_from: str | None = None
    repair_count: int = 0
    hand_edited: bool = False
    pending_operation: Operation | None = None
    stamps: dict = field(default_factory=dict)
    visuals_reviewed: bool = True
    ever_published: bool = False        # nodes are never published on their own


@dataclass
class RevisionRecord:
    id: int
    state: str = "AwaitingBrief"
    brief: dict | None = None
    proposal: dict | None = None        # the outline the model offered
    committed_outline: list | None = None
    outline_version: int = 0
    nodes: dict = field(default_factory=dict)
    forked_from: int | None = None
    ever_published: bool = False
    blocked_at: str | None = None
    blocked_from: str | None = None
    repair_count: int = 0
    pending_operation: Operation | None = None
    stamps: dict = field(default_factory=dict)
    approvals: list = field(default_factory=list)
    permission_checked: set = field(default_factory=set)
    used_restricted: set = field(default_factory=set)
    stale_nodes: set = field(default_factory=set)
    affected: bool = False
    re_verified: bool = False
    screened: dict = field(default_factory=dict)   # artifact → last verdict
    stale_via: str | None = None        # the event that sent it to StaleReview
    awaiting_pointer: bool = False      # published, and the pointer has not moved yet


@dataclass
class Store:
    config: dict
    current: dict                       # policy · guardrail · catalog · kb in force
    revisions: dict = field(default_factory=dict)
    live_pointer: int | None = None
    used_keys: set = field(default_factory=set)
    steps: list = field(default_factory=list)
    readers: dict = field(default_factory=dict)   # revision → learners mid-course

    def budget(self) -> int:
        return self.config["thresholds"]["repair_budget"]

    def new_revision(self, forked_from: int | None = None) -> RevisionRecord:
        rid = max(self.revisions, default=0) + 1
        rev = RevisionRecord(rid, forked_from=forked_from)
        self.revisions[rid] = rev
        return rev

    def snapshot(self, rev: RevisionRecord) -> dict:
        live = [n for n in rev.nodes.values()]
        return {
            "revision": rev.id,
            "course_state": rev.state,
            "node_states": {n.id: n.state for n in live},
            "retry_budget_left": {n.id: n.repair_count < self.budget() for n in live},
            "committed_outline": list(rev.committed_outline) if rev.committed_outline is not None else None,
            "approved_nodes": sorted(n.id for n in live if n.state == "NodeApproved"),
            "permission_checked": sorted(rev.permission_checked),
            "used_restricted": sorted(rev.used_restricted),
            "stale_nodes": sorted(rev.stale_nodes),
            "policy_version": rev.stamps.get("policy", self.current["policy"]),
            "current_policy_version": self.current["policy"],
            "guardrail_version": rev.stamps.get("guardrail", self.current["guardrail"]),
            "current_guardrail_version": self.current["guardrail"],
            "affected": rev.affected,
            "live_pointer": self.live_pointer,
            "revision_states": {r.id: r.state for r in self.revisions.values()},
            "forked_from": {r.id: r.forked_from for r in self.revisions.values()
                            if r.forked_from is not None},
            "re_verified": sorted(r.id for r in self.revisions.values() if r.re_verified),
        }
