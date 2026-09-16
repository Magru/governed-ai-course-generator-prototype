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
from .store import NodeRecord, Operation

#: Which event would have answered an operation issued from each state.
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


def _advance_outline(m, t, rev, old, payload):
    proposal = payload.get("outline") or rev.proposal
    rev.proposal = proposal
    rev.outline_version += 1
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
    rev.stamps = dict(m.store.current)
    rev.re_verified = True


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
}


def on_event(m, machine: str, obj, event: str, payload: dict) -> None:
    """Facts an event carries, recorded before its guards are read.

    An approval is recorded when it is given, not when it suffices: the
    inventory says "an approval that was not recorded did not happen", and a
    signature that arrives one short of the chain is still a signature.
    """
    rev = obj if machine == "revision" else m.rev_of(obj)
    if event == "BriefSubmitted" and machine == "revision":
        rev.brief = payload["brief"]
    elif event == "OutlineGenerated":
        rev.proposal = payload["outline"]
        m.store.used_keys.add(payload["idempotency_key"])
    elif event == "NodeGenerated" and machine == "node":
        obj.content = payload["content"]
        obj.hand_edited = False
        m.store.used_keys.add(payload["idempotency_key"])
    elif event == "NodeEdited" and machine == "node":
        obj.content = payload.get("content", obj.content)
        obj.hand_edited = True
    elif event == "GuardrailVerdict":
        key = obj.id if machine == "node" else payload.get("artifact", "revision")
        rev.screened[key] = {"verdict": payload["verdict"],
                             "guardrail_version": m.store.current["guardrail"]}
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
            obj.blocked_at, obj.blocked_from = PHASE_OF.get(issued, "node"), issued
        if old == "BlockedRecoverable" and new != old:
            obj.blocked_at = obj.blocked_from = None
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
        if new == "StaleReview":
            obj.re_verified = False
        if new == "Published" and old == "Approved":
            obj.ever_published = True
    else:
        if new == "NodeRecovery" and old != new:
            obj.pending_operation = Operation(
                payload.get("idempotency_key") or f"{obj.id}:{len(m.store.steps)}",
                old, AWAITED[("node", old)], dict(payload))
        if old == "NodeRecovery" and new != old:
            obj.pending_operation = None
        if old == "NodeRepair" and new == "ContentDrafting":
            obj.repair_count += 1
        if new == "NodeApproved":
            obj.stamps = dict(m.store.current)
            obj.repair_count = 0         # "since the last approval"
            m.rev_of(obj).approvals.append({
                "actor": payload.get("actor"), "scope": obj.id,
                "at": payload.get("event_time"),
                "what_was_shown": payload.get("what_was_shown")})
    if t.note:
        NOTES[t.note](m, t, obj, old, payload)
