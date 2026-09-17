"""A repeat is a no-op; a new round of verification is a new act; a notice
sent is remembered by the store, not by the object that sent it."""
from __future__ import annotations

import copy

import pytest

from gateway.membrane import Membrane
from scenarios import cassette, run, walkthrough as w


def _approved_course():
    screener = cassette.course_screener()
    screener.verdicts[("node-out", w.T2)] += ["allow"] * 3      # the edits below
    p = run.pipeline(screener=screener)
    m = p.machine
    p.submit_brief(copy.deepcopy(w.BRIEF), run.AUTHOR)
    while m.current.state == "OutlineDrafting":
        p.draft_outline(run.AUTHOR)
    m.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    for node in (w.T1, w.T2, w.T3):
        p.generate_node(node, run.AUTHOR)
        run.approve(p, node, **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if node == w.T1 else {}))
    p.generate_node(w.E1, run.AUTHOR)
    run.approve(p, w.E1)
    return p


def _edit(p, text):
    content = copy.deepcopy(w.CONTENT[w.T2])
    if text:
        content["blocks"][0]["text"] = text
    p.machine.fire("NodeEdited", {"node": w.T2, "content": content})
    p._screen_node(w.T2)


def _approve(p, node):
    return p.membrane.request("approve_node", {"node": node, "what_was_shown": "formal verdict"},
                              run.AUTHOR)


@pytest.fixture
def course():
    return _approved_course()


def test_a_double_click_is_already_done(course):
    _edit(course, "check every tool for splits before use")
    first, again = _approve(course, w.T2), _approve(course, w.T2)
    assert first.ran and (again.ran, again.check) == (False, "idempotency_key_unused")


def test_a_node_verified_again_with_the_same_content_can_be_approved_again(course):
    exam = course.machine.current.nodes[w.E1]
    before = copy.deepcopy(exam.content)
    _edit(course, "check every tool for splits before use")
    assert exam.state != "NodeApproved" and exam.content == before
    assert _approve(course, w.T2).ran
    out = _approve(course, w.E1)
    assert out.ran, out
    assert course.machine.current.nodes[w.E1].state == "NodeApproved"


def test_an_edit_reverted_to_its_first_wording_is_screened_and_approved_again(course):
    _edit(course, "check every tool for splits before use")
    assert _approve(course, w.T2).ran
    _edit(course, None)                                   # back to the original text
    node = course.machine.current.nodes[w.T2]
    assert node.state == "Validated", node.state
    assert _approve(course, w.T2).ran


def test_a_notice_sent_is_not_sent_again_by_a_restarted_gateway():
    p = run.the_course()
    args = {"notice": run.NOTICE, "recipients": 40}
    clean = lambda key: {"notice_screening": {"verdict": "allow", "guardrail_version": "guard-1"}}
    restarted = Membrane(p.machine, p.course)
    again = restarted.request("notify_learners", args, run.ADMIN, perform=clean)
    assert (again.ran, again.check) == (False, "idempotency_key_unused")
    correction = restarted.request("notify_learners", {**args, "notice": "A correction."}, run.ADMIN,
                                   perform=clean)
    assert correction.ran


def test_an_exam_is_not_approved_while_the_topic_it_tests_is_in_repair(course):
    """An exam approved while its topic was being repaired would be approved
    against content that no longer exists once the repair lands."""
    m = course.machine
    refused = copy.deepcopy(w.CONTENT[w.T2])
    refused["blocks"][0]["text"] = "wording the guardrail refuses"
    m.fire("NodeEdited", {"node": w.T2, "content": refused})
    m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "deny", "category": "unsafe"})
    assert _approve(course, w.E1).check == "legal_in_state"    # the topic is still in repair
    m.fire("NodeGenerated", {"node": w.T2, "content": copy.deepcopy(w.CONTENT[w.T2]),
                             "idempotency_key": "regenerated"})
    m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "allow"})
    assert _approve(course, w.T2).ran
    assert _approve(course, w.E1).ran
    assert m.current.state == "ReadyForReview"


def test_an_exam_rejected_while_its_topic_is_in_repair_waits_for_the_topic(course):
    from engines.temporal import engine as temporal
    from machine.refusal import MachineRefused
    m = course.machine
    edit = copy.deepcopy(w.CONTENT[w.T2])
    edit["blocks"][0]["text"] = "wording to be repaired"
    m.fire("NodeEdited", {"node": w.T2, "content": edit})
    m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "deny", "category": "unsafe"})
    m.fire("NodeRejected", {"node": w.E1, "reason": "question two is ambiguous", "actor": "author-1"})
    assert m.current.nodes[w.E1].state == "NodeRepair"
    with pytest.raises(MachineRefused):
        m.fire("NodeGenerated", {"node": w.E1, "content": copy.deepcopy(w.CONTENT[w.E1]),
                                 "idempotency_key": "too-early"})
    m.fire("NodeGenerated", {"node": w.T2, "content": copy.deepcopy(w.CONTENT[w.T2]),
                             "idempotency_key": "t2-repaired"})
    m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "allow"})
    assert _approve(course, w.T2).ran
    assert m.current.nodes[w.E1].state == "ContentDrafting"
    assert temporal.check(m.trace()).ok
