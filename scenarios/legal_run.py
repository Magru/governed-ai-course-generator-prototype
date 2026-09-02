"""One run that breaks nothing, shaped like the walkthrough.

Every negative test in the temporal suite is this run with a single field
changed. That is the point of it: a walk that refuses every legal run — and four
of them did — is invisible when each property is tested against a bespoke
two-step trace built to fail. Against a shared legal run it is the first thing
that shows.

The course is the Meridian Tools brief: two topics and an exam over both.
"""
from __future__ import annotations

COURSE = "mt-course-001"
N1, N2, EXAM = "mt-node-001", "mt-node-002", "mt-node-003"
OUTLINE = [N1, N2, EXAM]

# The envelope every event must carry. `event-catalog.yaml` says what breaks
# without each field; carrying them here is what lets the run be checked rather
# than assumed. Stamped by the builder so the run stays readable.
_SIDE_EFFECTING = {"OutlineGenerated", "NodeGenerated", "GuardrailVerdict",
                   "LivePointerMoved", "LearnersNotified"}


class Run:
    """Carries state forward so a fact is written once and stays written.

    A trace assembled as independent dicts loses a field the moment a step
    forgets to restate it, and a lost field is now a refusal — correctly, but it
    would be a refusal about the test rather than about the system.
    """

    #: A store holds every one of these at all times. A run that omits one is
    #: refused as undecidable — correctly — so the defaults are here rather
    #: than repeated at the top of every fragment.
    DEFAULTS = dict(revision=1, course_state="AwaitingBrief", node_states={},
                    retry_budget_left={}, committed_outline=None,
                    approved_nodes=[],
                    permission_checked=[], used_restricted=[], stale_nodes=[],
                    policy_version="p12", current_policy_version="p12",
                    guardrail_version="g4", current_guardrail_version="g4",
                    affected=True, live_pointer=None,
                    revision_states={1: "AwaitingBrief"}, forked_from={},
                    re_verified=[])

    def __init__(self, **initial) -> None:
        initial = {**{k: (v.copy() if hasattr(v, "copy") else v)
                      for k, v in self.DEFAULTS.items()}, **initial}
        self.state = dict(initial)
        self.steps = [{"event": "(initial)", **initial}]

    def then(self, event: str, *, nodes: dict | None = None,
             revisions: dict | None = None, payload: dict | None = None,
             **changes) -> "Run":
        if nodes:
            changes["node_states"] = {**self.state.get("node_states", {}), **nodes}
        if revisions:
            changes["revision_states"] = {**self.state.get("revision_states", {}),
                                          **revisions}
        self.state = {**self.state, **changes}
        step = {"event": event, **self.state, **(payload or {})}
        n = len(self.steps)
        step.update(event_id=f"e{n:03d}", event_time=f"2026-09-01T10:{n:02d}:00Z",
                    producer="orchestrator", correlation_id="rev-1",
                    causation_id=f"e{n - 1:03d}", schema_version="1")
        if event in _SIDE_EFFECTING:
            step["idempotency_key"] = f"{event}:{n}"
        self.steps.append(step)
        return self

    def build(self) -> list[dict]:
        return [dict(s) for s in self.steps]


def _generate_and_admit(run: Run, node: str, budget: dict, **payload) -> Run:
    """The node machine, one node's worth.

    ContentDrafting → Generated → OutputGuardrail → NodeChecks → Validated.
    The guardrail verdict is the step that admits the content to the record,
    which is what I6 is about and why the node is not in an admitted state
    before it.
    """
    run.then("NodeGenerationRequested", nodes={node: "ContentDrafting"},
             retry_budget_left={**budget, node: True})
    run.then("NodeGenerated", nodes={node: "Generated"},
             payload={"node": node, **payload})
    run.then("GuardrailVerdict", nodes={node: "NodeChecks"},
             payload={"artifact": node})
    run.then("(auto)", nodes={node: "Validated"})
    run.then("NodeApproved", nodes={node: "NodeApproved"},
             approved_nodes=sorted({*run.state.get("approved_nodes", []), node}),
             payload={"node": node})
    return run


def _base() -> Run:
    run = Run()

    run.then("BriefSubmitted", course_state="BriefValidation")
    run.then("OutlineGenerated", course_state="OutlineDrafting",
             nodes={n: "Planned" for n in OUTLINE})
    run.then("GuardrailVerdict", payload={"artifact": "outline"})
    run.then("OutlineApproved", course_state="ContentInProgress",
             committed_outline=list(OUTLINE), revisions={1: "ContentInProgress"})

    budget = {}
    _generate_and_admit(run, N1, budget)
    _generate_and_admit(run, N2, budget)
    # The exam is generated only once both topics stand approved together —
    # which is the moment I2 requires to exist somewhere in the past.
    _generate_and_admit(run, EXAM, budget, node_type="exam", topics=[N1, N2])

    run.then("CourseChecksRequested", course_state="WholeCourseChecks",
             revisions={1: "WholeCourseChecks"})
    run.then("(auto)", course_state="PendingApproval",
             revisions={1: "PendingApproval"})
    run.then("ApprovalGranted", course_state="Approved", revisions={1: "Approved"})
    run.then("PublishRequested", course_state="Published", revisions={1: "Published"})
    run.then("LivePointerMoved", live_pointer=1)
    run.then("LearnersNotified")
    return run


def legal_run() -> list[dict]:
    """Brief to publication, nothing refused along the way."""
    return _base().build()


def legal_removal() -> list[dict]:
    """A node dropped the way the model allows it: through a re-committed outline.

    The commit that drops the node and the removal are one transition. There is
    no earlier moment at which an outline excluding the node exists, so a strict
    past operator here forbids the only legal way to remove anything.
    """
    run = Run(revision=1, course_state="ContentInProgress",
              node_states={N1: "NodeApproved", N2: "Planned"},
              committed_outline=[N1, N2], approved_nodes=[N1])
    run.then("OutlineRevised", course_state="OutlineDrafting",
             committed_outline=[N1], nodes={N2: "Removed"})
    return run.build()


def legal_rollback() -> list[dict]:
    """Revision 2 supersedes 1, then the editor rolls back to 1.

    Rollback is not a restore: revision 1 re-enters through StaleReview and has
    to earn the pointer again, so the re-verification is genuinely in the past
    of the pointer moving back.
    """
    run = Run(revision=2, course_state="Published", live_pointer=1,
              revision_states={1: "Published", 2: "Approved"},
              forked_from={2: 1}, re_verified=[])
    run.then("LivePointerMoved", live_pointer=2,
             revisions={1: "Superseded", 2: "Published"})
    run.then("RollbackRequested", revisions={1: "StaleReview"})
    run.then("(auto)", re_verified=[1], revisions={1: "Approved"})
    run.then("LivePointerMoved", live_pointer=1,
             revisions={1: "Published", 2: "Superseded"},
             payload={"rolled_back_to": 1})
    return run.build()


def legal_restricted_source() -> list[dict]:
    """A node cites a restricted chunk after its audience rights were checked."""
    run = Run(revision=1, course_state="ContentInProgress",
              permission_checked=[], used_restricted=[])
    run.then("(auto)", permission_checked=[N1])
    run.then("NodeGenerated", used_restricted=[N1], payload={"node": N1},
             node_states={N1: "Generated"})
    return run.build()


def legal_held_node() -> list[dict]:
    """A node spends its last retry and the revision stops with it.

    The transition table keys the revision's move to BlockedRecoverable on the
    node reaching NodeRecovery with no budget, so both happen at once and the
    resulting state is the one to read.
    """
    run = Run(revision=1, course_state="ContentInProgress",
              node_states={N1: "OutputGuardrail"}, retry_budget_left={N1: True})
    run.then("Timeout", nodes={N1: "NodeRecovery"}, retry_budget_left={N1: False},
             course_state="BlockedRecoverable")
    return run.build()


#: Runs the specification declares legal. Every one of them must pass, and a
#: walk that refuses one of them is refusing the system it was written to guard.
#: `legal_rollback` is deliberately absent — see the contradiction it exposes,
#: which is a fault in the model rather than in the walk.
LEGAL = {"the happy path": legal_run,
         "a node removed through a re-committed outline": legal_removal,
         "a restricted source used after a rights check": legal_restricted_source,
         "a node that has spent its retries": legal_held_node}


def mutate(run: list[dict], step: int, **changes) -> list[dict]:
    """One legal run, one field changed — which is how every negative test here
    is built. A trace written from scratch to fail proves the check can fire; it
    proves nothing about whether the check also lets a legal run through."""
    out = [dict(s) for s in run]
    out[step] = {**out[step], **changes}
    return out


def find(run: list[dict], event: str, occurrence: int = 0) -> int:
    hits = [i for i, s in enumerate(run) if s["event"] == event]
    if len(hits) <= occurrence:
        raise AssertionError(f"the run has no {event!r} at index {occurrence}; "
                             f"it has {sorted({s['event'] for s in run})}")
    return hits[occurrence]
