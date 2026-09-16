"""The seven endpoints that are not state names.

`transitions.yaml` keeps them verbatim and lists them under
`open_questions.unresolved_endpoints`, with the note that each needs a
resolution rule before the tables can drive anything. These are the rules. Each
is keyed by the raw text, so a reworded endpoint is unknown rather than silently
matched, and each cites the glossary sentence it implements.

A *source* resolver answers "may this row fire from where the object stands?".
A *target* resolver answers "where does it go?". Both read the machine, not
the table text.
"""
from __future__ import annotations

from typing import Callable

#: Revision states a live revision can be in — `in_live_lineage`: "Published,
#: Superseded, StaleReview, and the ErrorRecovery or BlockedRecoverable a
#: re-verification can fall into".
LIVE_LINEAGE = {"Published", "Superseded", "StaleReview", "ErrorRecovery",
                "BlockedRecoverable"}

#: Terminal revision states. A draft that has reached one is not discarded again.
TERMINAL = {"Archived", "BlockedFinal", "Withdrawn"}

#: `blocked_at` — "which phase a recoverable block was entered from — brief,
#: outline, or content, each a named set of states". The inventory spells the
#: third value `node`; the glossary says `content`. The inventory is the file a
#: store implements, so its spelling is used and the difference is recorded.
PHASE_OF = {
    "AwaitingBrief": "brief", "BriefValidation": "brief", "BriefFeasibility": "brief",
    "OutlineDrafting": "outline", "OutlineGuardrail": "outline",
    "OutlineChecks": "outline", "OutlineRepair": "outline", "OutlineReview": "outline",
    "ContentInProgress": "node", "ReadyForReview": "node",
    "WholeCourseChecks": "node", "PendingApproval": "node", "Approved": "node",
}


def _live_lineage(machine, obj) -> bool:
    # The row's guard asks in_live_lineage as well. The source set is the
    # states; the guard is the revision's history. Both must hold.
    return obj.state in LIVE_LINEAGE


def _non_terminal_draft(machine, obj) -> bool:
    return obj.state not in TERMINAL and not obj.ever_published


def _not_removed(machine, obj) -> bool:
    return obj.state != "Removed"


def _state_that_blocked(machine, obj) -> str:
    # Entering BlockedRecoverable records the state it left; returning there is
    # "the fix returns there instead of to the beginning".
    return obj.blocked_from


def _state_after_operation(machine, obj) -> str:
    # The write landed: continue as if the operation's answer had arrived —
    # which is where the table sends the awaited event from the issuing state.
    return machine.landing_state(obj, obj.pending_operation)


def _state_that_issued(machine, obj) -> str:
    return obj.pending_operation.issued_from


def _course_blocked(machine, obj) -> tuple[str, str]:
    # Not a node state. The node stays where it is and its revision stops.
    return ("revision", "BlockedRecoverable")


SOURCES: dict[str, Callable] = {
    "any state in the live lineage": _live_lineage,
    "any non-terminal draft state": _non_terminal_draft,
    "any state but Removed": _not_removed,
}

TARGETS: dict[str, Callable] = {
    "the state that blocked": _state_that_blocked,
    "the state after the operation": _state_after_operation,
    "the state that issued the operation": _state_that_issued,
    "course → BlockedRecoverable": _course_blocked,
}
