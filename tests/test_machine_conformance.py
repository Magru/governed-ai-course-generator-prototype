"""What the machine must refuse, and what its trace must be able to show.

Each test is a concrete way the machine could accept something the tables do
not permit, or record a run in which an invariant could never have fired. The
second kind matters as much as the first: a temporal check that passes on a
trace where its antecedent never occurs has checked nothing.
"""
from __future__ import annotations

import copy
import shutil

import pytest

from engines.contract import EngineUnavailable
from engines.temporal import engine as temporal
from machine.machine import MachineRefused
from scenarios import walkthrough
from scenarios.machine_runs import (CONTENT, EXAM, N1, N2, OUTLINE, SIGNATURES, happy_path,
                                    machine, node_through, to_content, to_outline_review)


def _leaking():
    content = copy.deepcopy(CONTENT[N1])
    content["cites"] = ["mt-kb-008"]
    return content


def _held_in_repair(m):
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    for _ in range(m.store.budget() + 1):
        m.fire("NodeGenerated", {"node": N1, "content": _leaking()})
        m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N1, "node": N1})


# ── the trace can show what the invariants look for ──────────────────────────

def test_an_exam_generation_carries_what_i2_reads_and_i2_can_fire_on_it():
    m, _ = walkthrough.run()
    trace = m.trace()
    at = next(i for i, s in enumerate(trace)
              if s["event"] == "NodeGenerated" and s.get("node_type") == "exam")
    assert trace[at]["topics"] == [walkthrough.T1, walkthrough.T2, walkthrough.T3]
    broken = [dict(s, approved_nodes=[]) if i <= at else s for i, s in enumerate(trace)]
    assert temporal.check(broken).refusal.summary.startswith("I2 violated")


def test_a_sweep_that_reaches_a_revision_marks_it_affected_on_the_step_about_it():
    m = happy_path()
    m.fire("ReviseRequested", {"revision": 1})
    m.screener = None                          # re-verification cannot finish
    with pytest.raises(MachineRefused):
        m.fire("PolicyChanged", {"to": "pol-2"})
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {1: True, 2: False}})
    step = m.trace()[-1]
    assert (step["event"], step["revision"], step["course_state"], step["affected"]) == \
        ("PolicyChanged", 1, "StaleReview", True)


# ── conformance ──────────────────────────────────────────────────────────────

def test_an_approval_cannot_commit_an_outline_that_was_not_checked():
    m = machine()
    to_outline_review(m)
    invented = copy.deepcopy(OUTLINE)
    invented["nodes"][0]["skill"] = "post-mortem-facilitation"
    with pytest.raises(MachineRefused, match="differs from the one checked"):
        m.fire("OutlineApproved", {"outline": invented})
    assert m.current.state == "OutlineReview" and m.current.committed_outline is None


def test_nodes_are_not_removed_by_an_outline_approval_the_revision_refused():
    m = machine()
    to_content(m)
    without = {"nodes": [n for n in OUTLINE["nodes"] if n["id"] != N2]}
    with pytest.raises(MachineRefused):
        m.fire("OutlineApproved", {"outline": without, "reason": "dropped"})
    assert m.current.nodes[N2].state == "Planned"


def test_a_node_the_revision_does_not_have_is_refused():
    m = machine()
    to_content(m)
    with pytest.raises(MachineRefused, match="node ghost"):
        m.fire("NodeEdited", {"node": "ghost", "content": {}})


@pytest.mark.parametrize("to", [42, 2])
def test_the_pointer_moves_only_onto_a_published_revision(to):
    m = happy_path()
    m.fire("ReviseRequested", {"revision": 1})
    with pytest.raises(MachineRefused, match="pointer cannot move"):
        m.fire("LivePointerMoved", {"to": to})
    assert m.store.live_pointer == 1


def test_a_discarded_draft_stays_archived_whatever_its_nodes_are_doing():
    m = machine()
    _held_in_repair(m)
    assert m.current.state == "BlockedRecoverable"
    m.fire("DraftDiscarded", {"reason": "starting over"})
    assert m.current.state == "Archived"


def test_signatures_do_not_survive_the_revision_going_back_to_work():
    m = machine()
    to_content(m)
    for node in (N1, N2, EXAM):
        node_through(m, node)
        m.fire("NodeApproved", {"node": node, "actor": "author-1"})
    m.fire("CourseChecksRequested")
    m.fire("ApprovalGranted", {"signatures": SIGNATURES})
    m.fire("ReturnedToWork")
    m.fire("NodeEdited", {"node": N1, "content": copy.deepcopy(CONTENT[N1])})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N1, "node": N1})
    m.fire("NodeApproved", {"node": N1, "actor": "author-1"})
    if m.current.nodes[EXAM].state != "NodeApproved":
        m.fire("NodeApproved", {"node": EXAM, "actor": "author-1"})
    m.fire("CourseChecksRequested")
    with pytest.raises(MachineRefused, match="approval_chain_satisfied"):
        m.fire("ApprovalGranted", {"signatures": []})


def test_an_off_brief_topic_is_not_covered_at_its_own_checks():
    m = machine()
    outline = copy.deepcopy(OUTLINE)
    outline["nodes"][0]["skill"] = "noise-exposure"          # in the catalog, not in the brief
    to_outline_review(m, outline=outline)
    m.fire("OutlineApproved")
    m.fire("NodeGenerationRequested", {"node": N1})
    m.fire("NodeGenerated", {"node": N1, "content": copy.deepcopy(CONTENT[N1])})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N1, "node": N1})
    failed = next(s for s in reversed(m.trace()) if s["event"] == "CheckFailed")
    assert failed["node"] == N1
    # repairable since spec-v2.8: the node goes back to be rewritten
    assert (m.current.nodes[N1].state, m.current.nodes[N1].repair_count) == ("ContentDrafting", 1)


def test_a_policy_refusal_at_node_checks_is_terminal_for_the_node():
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    m.fire("NodeGenerated", {"node": N1, "content": copy.deepcopy(CONTENT[N1])})
    m.world.people["author-1"]["may_author_for"] = []        # the grant is withdrawn mid-run
    try:
        m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N1, "node": N1})
    finally:
        m.world.people["author-1"]["may_author_for"] = ["all-staff", "workshop-floor", "apprentices"]
    failed = next(s for s in reversed(m.trace()) if s["event"] == "CheckFailed")
    assert failed["node"] == N1
    assert (m.current.nodes[N1].state, m.current.state) == ("BlockedFinal", "BlockedRecoverable")


def test_a_person_clearing_a_block_restores_the_revisions_retries():
    m = machine()
    m.fire("BriefSubmitted", {"brief": copy.deepcopy(walkthrough.BRIEF)})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": "brief"})
    for _ in range(m.store.budget() + 1):
        m.fire("Timeout")
    assert (m.current.state, m.current.blocked_at) == ("BlockedRecoverable", "outline")
    m.fire("BlockedInputFixed", {"reason": "provider back"})
    assert (m.current.state, m.current.repair_count) == ("OutlineDrafting", 0)


# ── errors that are not refusals still leave nothing behind ─────────────────

def test_an_unknown_actor_is_a_policy_refusal_not_a_crash():
    m = machine()
    m.fire("BriefSubmitted", {"brief": copy.deepcopy(walkthrough.BRIEF), "actor": "mallory"})
    assert m.current.state == "BlockedFinal"


def test_an_engine_that_cannot_run_leaves_the_store_as_it_was(monkeypatch):
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    m.fire("NodeGenerated", {"node": N1, "content": copy.deepcopy(CONTENT[N1])})
    steps = len(m.trace())
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "swipl" else real(name))
    with pytest.raises(EngineUnavailable):
        m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N1, "node": N1})
    assert len(m.trace()) == steps
    assert m.current.nodes[N1].state == "OutputGuardrail"
