"""The action registry — safety.html §2, and nothing runs that is not in it.

Each entry carries what the specification's table carries: risk, side effect,
who must be behind it, and how it is compensated. Two columns are added, and
both are pointers rather than judgements: the event the action becomes on the
machine (so legality is the table's answer, not this file's), and the shape of
its arguments (closed — an unexpected field is refused, not ignored).

Who acts is never an argument either. It is the caller the membrane
authenticated, so no one can approve or publish in someone else's name.

Risk is a property of the action held here. It is never inferred at runtime
from anything a model produced.
"""
from __future__ import annotations

from dataclasses import dataclass

PERSON, SYSTEM, NOBODY = "person", "system", "nobody"

#: The events whose payload carries what a provider answered. Their result is
#: never an argument: a caller who could pass it could declare a screening
#: clean or a lesson written without asking anyone.
PRODUCED = {"OutlineGenerated": "outline", "NodeGenerated": "content", "GuardrailVerdict": "verdict",
            "LearnersNotified": "notice_screening"}


def _args(**properties) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": sorted(k for k, v in properties.items() if v.pop("required", True)),
            "properties": properties}


ID = {"type": "string", "minLength": 1}
TEXT = {"type": "string", "minLength": 1}


@dataclass(frozen=True)
class Action:
    name: str
    risk: str                    # low · medium · high · critical
    side_effect: str
    requires: str                # PERSON, SYSTEM or NOBODY — the Requires column
    compensation: str
    event: str | None            # what it becomes on the machine; None for a read
    args: dict
    enforced_downstream: str | None = None


REGISTRY = {a.name: a for a in [
    Action("retrieve_sources", "low", "none — read only", NOBODY, "nothing to undo", None,
           _args(query=dict(TEXT), audience={"type": "array", "items": ID}),
           enforced_downstream="rights re-checked by no_permission_leak at NodeChecks"),
    Action("propose_outline", "low", "none — a proposal, not state", NOBODY, "discard",
           "OutlineGenerated", _args(prompt=dict(ID))),
    Action("generate_node_content", "medium", "spends money, writes a draft", NOBODY,
           "discard the draft; the spend is sunk", "NodeGenerated",
           _args(node=dict(ID), prompt=dict(ID))),
    Action("generate_image", "medium", "spends money, external provider", NOBODY,
           "discard the draft — the prompt has already left the tenant", None,
           _args(node=dict(ID), prompt=dict(TEXT)),
           enforced_downstream="visual review is a condition of approve_node"),
    Action("admit_to_revision", "medium", "changes revision state", NOBODY,
           "node returns to NeedsRevalidation", "GuardrailVerdict",
           _args(artifact=dict(ID), screened=dict(ID),
                 node={"type": "string", "minLength": 1, "required": False})),
    Action("approve_node", "high", "stamps versions, records who saw what", PERSON,
           "an edit withdraws the approval and cascades", "NodeApproved",
           _args(node=dict(ID), what_was_shown=dict(TEXT),
                 visuals_reviewed={"type": "array", "items": TEXT, "required": False})),
    Action("publish_revision", "critical", "learners can see it", PERSON,
           "rollback — but only through re-verification", "PublishRequested",
           _args(revision={"type": "integer"})),
    Action("move_live_pointer", "critical", "changes what an audience is served", SYSTEM,
           "move it back, re-verifying first", "LivePointerMoved",
           _args(to={"type": "integer"}, rolled_back_to={"type": "integer", "required": False})),
    Action("withdraw_revision", "high", "learners lose access mid-course", PERSON,
           "a new revision through ReviseRequested", "WithdrawRequested",
           _args(revision={"type": "integer"}, reason=dict(TEXT))),
    Action("notify_learners", "critical", "irreversible — cannot be unsent", PERSON,
           "correction notice and incident record; there is no undo", "LearnersNotified",
           _args(notice=dict(TEXT), recipients={"type": "integer", "minimum": 0})),
    Action("archive_revision", "high", "removes from circulation", PERSON,
           "none — Archived is terminal", "ArchiveRequested",
           _args(revision={"type": "integer"})),
]}
