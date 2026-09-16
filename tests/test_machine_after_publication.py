"""After publication: the fork, the rollback, and a rule that changes.

Chains 3 and 4 of transitions.html §5, run through the machine. Both are
declared legal by the specification, both reach their declared end, and the
temporal engine accepts the machine's own trace of each. Until spec-v2.8 it
refused both — I12 the rollback, I11 the re-verification — and the model was
amended rather than the checker.
"""
from __future__ import annotations

import copy

import pytest

from engines.temporal import engine as temporal
from machine.machine import MachineRefused
from scenarios.machine_runs import CONTENT, EXAM, N2, SIGNATURES, happy_path


def _at(m, event: str) -> dict:
    return next(s for s in reversed(m.trace()) if s["event"] == event)


@pytest.fixture(scope="module")
def rolled_back():
    m = happy_path()
    m.screener = lambda rev, version: ("allow", version)
    m.fire("ReviseRequested", {"revision": 1})
    edited = copy.deepcopy(CONTENT[N2])
    edited["blocks"][0]["text"] = "check every tool before use, every time"
    m.fire("NodeEdited", {"node": N2, "content": edited})
    cascade = _at(m, "NodeEdited")
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N2, "node": N2})
    m.fire("NodeApproved", {"node": N2, "actor": "author-1"})
    m.fire("NodeApproved", {"node": EXAM, "actor": "author-1"})
    m.fire("CourseChecksRequested")
    m.fire("ApprovalGranted", {"signatures": SIGNATURES})
    m.fire("PublishRequested")
    after_second = dict(m.store.steps[-1])
    m.fire("RollbackRequested", {"revision": 1, "reason": "the new wording confused learners"})
    return m, cascade, after_second


def test_a_fork_edits_only_the_draft_and_the_cascade_reaches_the_exam(rolled_back):
    m, cascade, _ = rolled_back
    assert cascade["revision"] == 2
    assert cascade["node_states"][N2] == "NeedsRevalidation"
    # The exam was written against the topic, so it is no longer approved.
    exam_after = next(s for s in m.trace()[m.trace().index(cascade):]
                      if s["node_states"].get(EXAM) != "NodeApproved")
    assert exam_after["node_states"][EXAM] in {"NeedsRevalidation", "NodeChecks", "Validated"}
    assert cascade["revision_states"][1] == "Published"


def test_the_second_publication_supersedes_the_first_and_moves_the_pointer(rolled_back):
    _, _, after_second = rolled_back
    assert after_second["event"] == "LivePointerMoved"
    assert (after_second["revision_states"], after_second["live_pointer"]) == \
        ({1: "Superseded", 2: "Published"}, 2)


def test_a_rollback_is_a_reverification_and_then_a_pointer_move(rolled_back):
    m, _, _ = rolled_back
    events = [s["event"] for s in m.trace()]
    tail = events[events.index("RollbackRequested"):]
    assert tail == ["RollbackRequested", "(auto)", "LivePointerMoved"]
    last = m.trace()[-1]
    assert (last["revision_states"], last["live_pointer"], last["rolled_back_to"]) == \
        ({1: "Published", 2: "Superseded"}, 1, 1)
    assert 1 in last["re_verified"]


def test_the_machines_rollback_satisfies_every_invariant(rolled_back):
    verdict = temporal.check(rolled_back[0].trace())
    assert verdict.ok, verdict.refusal


def test_a_rule_change_re_verifies_what_it_reaches_and_leaves_the_rest_alone():
    m = happy_path()
    m.screener = lambda rev, version: ("allow", version)
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {1: True}})
    rev = m.store.revisions[1]
    assert (rev.state, rev.stamps["policy"], rev.stale_nodes) == ("Published", "pol-2", set())
    assert [s["event"] for s in m.trace()[-2:]] == ["PolicyChanged", "(auto)"]
    m.fire("PolicyChanged", {"to": "pol-3", "reaches": {1: False}})
    assert (rev.state, rev.stamps["policy"]) == ("Published", "pol-2")
    assert m.trace()[-1]["event"] == "PolicyChanged"


def test_a_change_nobody_judged_is_not_read_as_unaffected():
    m = happy_path()
    before = len(m.trace())
    with pytest.raises(MachineRefused, match="nothing judged whether the change reaches"):
        m.fire("PolicyChanged", {"to": "pol-2"})
    # refused whole: no step, and the policy in force did not move either
    assert (len(m.trace()), m.store.current["policy"]) == (before, "pol-1")


def test_a_rule_the_live_course_fails_withdraws_it():
    m = happy_path()
    m.screener = lambda rev, version: ("deny", version)
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {1: True}})
    assert m.store.revisions[1].state == "Withdrawn"


def test_a_live_revision_stays_on_air_while_it_is_re_verified():
    m = happy_path()
    m.screener = lambda rev, version: ("allow", version)
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {1: True}})
    during = next(st for st in m.trace() if st["event"] == "PolicyChanged")
    assert (during["revision_states"][1], during["live_pointer"]) == ("StaleReview", 1)
    verdict = temporal.check(m.trace())
    assert verdict.ok, verdict.refusal


def test_a_superseded_revision_that_passes_re_verification_stays_superseded():
    m = happy_path()
    m.screener = lambda rev, version: ("allow", version)
    m.store.readers = {1: 12}
    m.fire("ReviseRequested", {"revision": 1})
    edited = copy.deepcopy(CONTENT[N2])
    edited["blocks"][0]["text"] = "check every tool before use, every time"
    m.fire("NodeEdited", {"node": N2, "content": edited})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N2, "node": N2})
    m.fire("NodeApproved", {"node": N2, "actor": "author-1"})
    m.fire("NodeApproved", {"node": EXAM, "actor": "author-1"})
    m.fire("CourseChecksRequested")
    m.fire("ApprovalGranted", {"signatures": SIGNATURES})
    m.fire("PublishRequested")
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {1: True, 2: False}})
    rev1 = m.store.revisions[1]
    assert (rev1.state, rev1.stamps["policy"], m.store.live_pointer) == ("Superseded", "pol-2", 2)
    assert temporal.check(m.trace()).ok


def test_withdrawing_the_live_revision_cuts_access():
    m = happy_path()
    m.fire("WithdrawRequested", {"revision": 1, "reason": "a rule it breaks was found"})
    assert (m.store.revisions[1].state, m.store.live_pointer) == ("Withdrawn", None)
    assert temporal.check(m.trace()).ok


def test_an_unreachable_guardrail_spends_the_budget_and_the_emergency_lever_still_works():
    m = happy_path()

    def down(rev, version):
        raise ConnectionError("no route to the guardrail")

    m.screener = down
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {1: True}})
    events = [s["event"] for s in m.trace()]
    assert events.count("ServiceUnreachable") == m.store.budget() + 1
    rev = m.store.revisions[1]
    assert (rev.state, rev.blocked_at, rev.blocked_from) == \
        ("BlockedRecoverable", None, "StaleReview")
    # in_live_lineage: "an emergency lever wired only to Published would come
    # away in their hand" — withdrawal works from the block an outage caused.
    with pytest.raises(MachineRefused):
        m.fire("WithdrawRequested", {"revision": 1})
    m.fire("WithdrawRequested", {"revision": 1, "reason": "cannot re-screen; pull it"})
    assert m.store.revisions[1].state == "Withdrawn"


def test_a_verdict_from_the_version_being_replaced_is_no_answer():
    """Mid-rollout the service may still answer as the old guardrail. That verdict
    is not recorded under the new version; re-verification waits as for a timeout."""
    m = happy_path()
    m.screener = lambda rev, version: ("allow", "guard-1")
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {1: True}})
    assert "ServiceUnreachable" in [s["event"] for s in m.trace()]
    assert (m.store.revisions[1].screened.get("revision") or {}).get("guardrail_version") != "guard-2"
