"""What an action acts on — the half of the idempotency key the arguments do not carry.

The key must make a repeat a no-op and must not make a new act look like a
repeat. Arguments alone do both badly: approving the same node with the same
words is a double click in one round of verification and a legitimate new
approval in the next, and admitting content A, then B, then A again is three
admissions, not one.

So the subject names the revision, the content an approval or admission is
about, and the round of verification the object is in. A round begins each time
the object enters a state where it waits to be judged afresh. The count is read
from the trace the store already keeps: every step records the states after it,
so no new variable is needed and none can drift from the record.
"""
from __future__ import annotations

import hashlib
import json

#: Entering one of these starts a new round for a node: new content waiting
#: for its screening, or approved content that must be verified again.
NODE_ROUNDS = {"OutputGuardrail", "NeedsRevalidation"}
#: And for a revision: its brief or outline waiting for a screening, the
#: course waiting for signatures, a live course being verified again.
REVISION_ROUNDS = {"BriefValidation", "OutlineGuardrail", "PendingApproval", "StaleReview"}


def key_of(name: str, args: dict, course: str, subject: dict | None = None) -> str:
    """sha256 of the canonical action — the inventory's definition of the key."""
    canonical = json.dumps({"action": name, "args": args, "course": course,
                            "subject": subject or {}},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


#: Actions that land what a model made: the state an answer is asked from, and
#: the recovery state a retry of an unanswered call returns from.
DRAFTING = {"NodeGenerated": ("ContentDrafting", "NodeRecovery"),
            "OutlineGenerated": ("OutlineDrafting", "ErrorRecovery")}


def subject_of(machine, args: dict, event: str | None) -> dict:
    """A generation is named by its prompt digest and by how many times its
    object was sent to be drafted. A call that never answered is retried from
    recovery, which is not a new request, so it keeps the key and the provider
    deduplicates it — also when a person releases it from a block, because the
    call still never answered. A second press of the same request keeps it too
    and is 'already done'. A repair, a rejection, or an answer in the wrong shape
    asks again — and may ask with the same prompt — so it is a new act with a
    new key."""
    rev = machine.current
    node = rev.nodes.get(args.get("node")) if args.get("node") else None
    if event in DRAFTING:
        drafting, recovery = DRAFTING[event]
        # An answer in the wrong shape did not land, but it was an answer: asking
        # again under its key would get it back from a provider that deduplicates.
        errors = sum(1 for s in machine.store.steps if s.get("revision") == rev.id
                     and s["event"] == "ModelError" and s.get("node") == args.get("node"))
        return {"revision": rev.id, "model_errors": errors,
                "drafts": entries(machine.store.steps, rev.id, args.get("node"), drafting, recovery)}
    return {"revision": rev.id,
            "node": json.dumps(node.content, sort_keys=True) if node is not None else None,
            "round": rounds(machine.store.steps, rev.id, node.id if node is not None else None)}


def rounds(steps: list, revision: int, node: str | None) -> int:
    """How many times the object has entered a state that starts a round."""
    count, last = 0, None
    for step in steps:
        if step.get("revision") != revision:
            continue
        state = step["node_states"].get(node) if node else step["course_state"]
        if state != last and state in (NODE_ROUNDS if node else REVISION_ROUNDS):
            count += 1
        last = state
    return count


def entries(steps: list, revision: int, node: str | None, state: str, not_from: str) -> int:
    """How many times the object entered a state, other than back from one."""
    count, last = 0, None
    for step in steps:
        if step.get("revision") != revision:
            continue
        now = step["node_states"].get(node) if node else step["course_state"]
        count += now == state and last != state and last != not_from
        last = now
    return count
