"""What a transition writes, besides the state it moves to.

Two sources, kept apart on purpose.

NOTES are the side effects the tables write in the To column — `outline_version
+1`, `recovery_from = generation`. Each is keyed by its exact text, and the
loader refuses a note this module does not know, for the same reason it refuses
an unknown guard.

RULES are the ones the tables leave implicit and the glossary or the inventory
states in prose: when the repair counter rises, what entering a block records,
what an approval stamps. They are not invented — each cites its sentence — but
they are the prototype's reading of prose, and listing them is what lets a
reviewer disagree with one.
"""
from __future__ import annotations

from .endpoints import PHASE_OF


class ApprovalOfUncheckedOutline(RuntimeError):
    """Raised inside an event; the machine turns it into a refusal."""
from .store import NodeRecord, Operation

#: Which event would have answered an operation issued from each state.
#: A configuration change names the stamp it supersedes.
CHANGED = {"PolicyChanged": "policy", "GuardrailChanged": "guardrail",
           "CatalogChanged": "catalog", "KBUpdated": "kb"}

AWAITED = {
    ("revision", "BriefValidation"): "GuardrailVerdict",
    ("revision", "OutlineDrafting"): "OutlineGenerated",
    ("revision", "OutlineGuardrail"): "GuardrailVerdict",
    ("revision", "StaleReview"): "GuardrailVerdict",
    ("node", "ContentDrafting"): "NodeGenerated",
    ("node", "OutputGuardrail"): "GuardrailVerdict",
}


def _set_recovery(value):
    def effect(m, t, obj, old, payload):
        obj.recovery_from = value
    return effect


def _raise_repair(m, t, obj, old, payload):
    obj.repair_count += 1


def _reset_repair(m, t, obj, old, payload):
    obj.repair_count = 0


def _wait_for_topics(m, t, obj, old, payload):
    obj.waiting_for_topics = True


def _advance_outline(m, t, rev, old, payload):
    # Only the proposal that went through OutlineChecks is committed; on_event
    # has already refused an approval carrying a different one.
    proposal = rev.proposal
    rev.outline_version += 1
    rev.last_refusal = None       # settled by the approval, as a node's is
    rev.committed_outline = [n["id"] for n in proposal["nodes"]]
    for spec in proposal["nodes"]:
        if spec["id"] not in rev.nodes:
            rev.nodes[spec["id"]] = NodeRecord(spec["id"], dict(spec))
        else:
            rev.nodes[spec["id"]].spec = dict(spec)
    rev.repair_count = 0          # "since the last approval"


def _discard_proposal(m, t, rev, old, payload):
    rev.proposal = {"nodes": [rev.nodes[i].spec for i in rev.committed_outline or []]}


def _block_at_node(m, t, rev, old, payload):
    rev.blocked_at, rev.blocked_from = "node", old


def _restamp(m, t, rev, old, payload):
    # Re-judged against today's versions: the revision and every node on it
    # now carry them, and nothing on it is stale any more.
    rev.stamps = dict(m.store.current)
    for node in rev.nodes.values():
        if node.state != "Removed":
            node.stamps = dict(m.store.current)
    rev.stale_nodes.clear()
    rev.affected = False
    rev.re_verified = True
    # A revision re-verified on its way back from a rollback earns the pointer;
    # one re-verified because a rule changed under it already holds it.
    rev.awaiting_pointer = rev.stale_via == "RollbackRequested"


def _nothing(m, t, obj, old, payload):
    pass


def _spawn(m, t, rev, old, payload):
    m.fork(rev)


NOTES = {
    "outline_version +1": _advance_outline,
    "proposal discarded; outline_version unchanged": _discard_proposal,
    "blocked_at = node": _block_at_node,
    "spawn; this revision does not move": _spawn,
    "spawn": _spawn,
    "no move; the notice is recorded": _nothing,     # the step itself is the record
    "re-stamped": _restamp,
    "recovery_from = generation": _set_recovery("generation"),
    "recovery_from = guardrail": _set_recovery("guardrail"),
    "repair_count +1": _raise_repair,
    "repair_count = 0": _reset_repair,
    "waiting_for_topics": _wait_for_topics,
}


def on_event(m, machine: str, obj, event: str, payload: dict) -> None:
    """Facts an event carries, recorded before its guards are read.

    An approval is recorded when it is given, not when it suffices: the
    inventory says "an approval that was not recorded did not happen", and a
    signature that arrives one short of the chain is still a signature.
    """
    rev = obj if machine == "revision" else m.rev_of(obj)
    if event in CHANGED and machine == "revision":
        m.store.current[CHANGED[event]] = payload["to"]
    if event in ("OutlineApproved", "OutlineRejected") and machine == "revision":
        offered = payload.get("outline")
        if offered is not None and offered != rev.proposal:
            # An approval signs what was checked. An outline edited at review
            # has not been through schema, Datalog, OPA or Z3; committing it
            # here would be the one unchecked path into course structure.
            raise ApprovalOfUncheckedOutline(
                f"{event} carries an outline that differs from the one checked; "
                "the edit must go through OutlineRevised and OutlineChecks")
    if event == "OutlineRevised" and machine == "revision" and payload.get("outline"):
        rev.proposal = payload["outline"]
    if event == "NodeGenerationRequested" and machine == "node":
        obj.issued_key = payload.get("idempotency_key") or f"generate:{obj.id}:{len(m.store.steps)}"
    if payload.get("reason") and ((event == "OutlineRejected" and machine == "revision")
                                  or (event == "NodeRejected" and machine == "node")):
        # A person's reason is what the next draft is told, as a check's is.
        obj.last_refusal = payload["reason"]
    if event == "CheckFailed" or (event == "GuardrailVerdict" and payload.get("verdict") == "deny"):
        # What the repair prompt is told. Kept on the object the repair is for.
        reason = payload.get("reason") or payload.get("category")
        if reason:
            obj.last_refusal = reason
    if event == "BriefSubmitted" and machine == "revision":
        rev.brief = payload["brief"]
        # The checks that follow run as (auto) rows with no payload of their
        # own; OPA must judge the person who submitted, not a default.
        rev.author = payload.get("actor") or m.store.config["author"]
    elif event == "OutlineGenerated":
        rev.proposal = payload.get("outline")
        m.store.used_keys.add(payload["idempotency_key"])
    elif event == "NodeGenerated" and machine == "node":
        obj.content = payload.get("content")
        obj.hand_edited = False
        m.store.used_keys.add(payload["idempotency_key"])
    elif event == "NodeEdited" and machine == "node":
        obj.content = payload.get("content", obj.content)
        obj.hand_edited = True
    elif event == "GuardrailVerdict":
        key = obj.id if machine == "node" else payload.get("artifact", "revision")
        # The version that gave the verdict, as the event catalog requires the
        # payload to carry it. The store's version stands in only for an event
        # fired straight at the machine; the gateway always sends its own.
        rev.screened[key] = {"verdict": payload.get("verdict"),
                             "guardrail_version": payload.get("guardrail_version")
                             or m.store.current["guardrail"]}
    elif event == "ApprovalGranted" and machine == "revision":
        # approvals[] holds every approval with its scope; the publication chain
        # is the entries scoped to publication, never a node's approval.
        rev.approvals.extend({**sig, "scope": "publication"}
                             for sig in payload.get("signatures") or [])


def after_transition(m, t, obj, old: str, payload: dict) -> None:
    """The implicit rules, then the row's own note."""
    new = obj.state
    # Branch on the object, not the row: a node row can stop its revision, and
    # what that writes is the revision's bookkeeping.
    if hasattr(obj, "approvals"):
        if new == "BlockedRecoverable" and old != "BlockedRecoverable":
            # glossary, blocked_at: "which phase a recoverable block was entered
            # from … so the fix returns there instead of to the beginning".
            issued = obj.pending_operation.issued_from if old == "ErrorRecovery" else old
            # A live revision blocked during re-verification is in none of the
            # three phases; it records no phase, and its way back is still the
            # state that blocked.
            obj.blocked_at, obj.blocked_from = PHASE_OF.get(issued), issued
        if old == "BlockedRecoverable" and new != old:
            obj.blocked_at = obj.blocked_from = None
            # A person cleared the cause: the counter restarts, as the node
            # rows out of NodeRecovery say explicitly for the node machine.
            obj.repair_count = 0
        if new == "ContentInProgress" and old != new:
            # Consent is to this version. Signatures given before the revision
            # went back to work are for a course that no longer exists.
            obj.approvals = [a for a in obj.approvals if a.get("scope") != "publication"]
        if new == "Approved" and old == "PendingApproval":
            # walkthrough step 23: "the course is stamped as a whole, the same
            # way each node was".
            obj.stamps = dict(m.store.current)
        if new == "ErrorRecovery" and old != new:
            obj.pending_operation = Operation(
                payload.get("idempotency_key") or f"{old}:{obj.id}:{len(m.store.steps)}",
                old, AWAITED[("revision", old)], dict(payload))
        if old == "ErrorRecovery" and new != old:
            if new == obj.pending_operation.issued_from:
                obj.repair_count += 1    # "every retry taken out of recovery"
            obj.pending_operation = None
        if old == "OutlineRepair" and new == "OutlineDrafting":
            obj.repair_count += 1        # a repair is a retry that changed the request
        if new == "BriefValidation":
            # walkthrough step 2: "writes: policy_version · guardrail_version"
            obj.stamps.update({k: m.store.current[k] for k in ("policy", "guardrail")})
        if new == "StaleReview" and old != new:
            obj.re_verified = False
            obj.stale_via = payload.get("event") or t.event
            obj.affected = obj.stale_via in CHANGED
            # stale_nodes is written by the sweep that found this revision
            # affected, not derived from every stamp that is behind: an
            # unaffected revision stays Published under an old stamp, which
            # is exactly what I7 and I15 permit and a derived list would forbid.
            obj.stale_nodes = {n.id for n in obj.nodes.values()
                               if n.state != "Removed" and any(
                                   m.store.current[k] != v for k, v in n.stamps.items())}
        if new == "Withdrawn" and m.store.live_pointer == obj.id:
            # Access is cut (decision 28.07; I11 as amended 16.09): a withdrawn
            # revision is served to nobody, so the pointer is cleared rather
            # than left naming it.
            m.store.live_pointer = None
        if new == "Published" and old == "Approved":
            obj.ever_published = True
            obj.awaiting_pointer = True
    else:
        if new == "NodeRecovery" and old != new:
            obj.pending_operation = Operation(
                payload.get("idempotency_key") or getattr(obj, "issued_key", None)
                or f"{obj.id}:{len(m.store.steps)}",
                old, AWAITED[("node", old)], dict(payload))
        if old == "NodeRecovery" and new != old:
            obj.pending_operation = None
        if old == "NodeRepair" and new == "ContentDrafting":
            # A repair is a retry. An exam sent back because a topic it tests
            # changed failed nothing, so its way out is not one.
            obj.repair_count += not obj.waiting_for_topics
        if old == "NodeRepair" and new != old:
            obj.waiting_for_topics = False
        if new == "NodeApproved":
            # What an earlier attempt was refused for is settled; a later repair
            # told it would mend something that is no longer wrong.
            obj.last_refusal = None
            obj.stamps = dict(m.store.current)
            obj.repair_count = 0         # "since the last approval"
            m.rev_of(obj).approvals.append({
                "actor": payload.get("actor"), "scope": obj.id,
                "at": payload.get("event_time"),
                "what_was_shown": payload.get("what_was_shown")})
    if t.note:
        NOTES[t.note](m, t, obj, old, payload)
