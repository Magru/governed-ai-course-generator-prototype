"""A draft is finished under the rules in force when it is published.

A node is stamped with the versions its checks ran under, so a guardrail
replaced between screening and approval leaves it stale rather than passing it.
A configuration change sends a draft's checked nodes back through the guardrail
and the checks, and a draft already in review back to work. An outline that
gives an exam a new topic makes the exam wait for it, and an exam is approved
only over topics that stand approved.
"""
from __future__ import annotations

import copy

from engines.temporal import engine as temporal
from gateway.provider.port import Screener, Verdict
from gateway.provider.recorded import RecordedGenerator
from scenarios import run, walkthrough as w


class Screening(Screener):
    version = "guard-1"

    def screen(self, content, modality, point, subject=""):
        return Verdict(True, None, self.version, point)


def _ready(nodes=(w.T1, w.T2, w.T3, w.E1), approved=(w.T1, w.T2, w.T3, w.E1)):
    answers = {f"node:{n}": [copy.deepcopy(w.CONTENT[n])] for n in (w.T1, w.T2, w.T3, w.E1)}
    p = run.pipeline(generator=RecordedGenerator({"outline": [copy.deepcopy(w.OUTLINE)], **answers}),
                     screener=Screening())
    p.submit_brief(copy.deepcopy(w.BRIEF), run.AUTHOR)
    p.draft_outline(run.AUTHOR)
    p.machine.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    for node in nodes:
        p.generate_node(node, run.AUTHOR)
        if node in approved:
            run.approve(p, node, **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if node == w.T1 else {}))
    return p


def _approve_all(p):
    for node in (w.T1, w.T2, w.T3, w.E1):
        run.approve(p, node, **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if node == w.T1 else {}))


def test_a_guardrail_replaced_while_a_draft_is_in_review_sends_it_back_to_be_screened_again():
    p = _ready()
    m = p.machine
    assert m.current.state == "ReadyForReview"
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {}})
    assert m.current.state == "ContentInProgress"
    assert {n.state for n in m.current.nodes.values()} == {"OutputGuardrail"}

    p.screener.version = "guard-2"
    p.screen_waiting()
    _approve_all(p)
    assert all(n.stamps["guardrail"] == "guard-2" for n in m.current.nodes.values())
    run.publish(p)
    assert m.current.state == "Published"
    assert temporal.check(m.trace()).ok


def test_a_node_screened_before_the_change_and_approved_after_it_is_stale():
    p = _ready(nodes=(w.T1, w.T2), approved=(w.T1,))
    m = p.machine
    assert m.current.nodes[w.T2].state == "Validated"  # screened and checked under guard-1
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {}})
    assert m.current.nodes[w.T2].state == "OutputGuardrail"   # not approvable on the old screening
    p.screener.version = "guard-2"
    p.screen_waiting()
    run.approve(p, w.T2)
    assert m.current.nodes[w.T2].stamps["guardrail"] == "guard-2"


def test_an_outline_that_gives_a_drafting_exam_a_new_topic_makes_it_wait():
    p = _ready(nodes=(w.T1, w.T2, w.T3))
    m = p.machine
    m.fire("NodeGenerationRequested", {"node": w.E1, "actor": run.AUTHOR["id"]})
    assert m.current.nodes[w.E1].state == "ContentDrafting"
    outline = copy.deepcopy(m.current.proposal)
    extra = {**copy.deepcopy(next(n for n in outline["nodes"] if n["id"] == w.T3)), "id": "mt-node-205"}
    outline["nodes"].insert(3, extra)
    next(n for n in outline["nodes"] if n["id"] == w.E1)["topics"].append("mt-node-205")
    m.fire("OutlineRevised", {"outline": outline, "actor": run.AUTHOR["id"]})
    m.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    assert m.current.nodes[w.E1].state == "NodeRepair"
    assert temporal.check(m.trace()).ok


def test_a_notice_to_more_learners_than_the_approvers_were_shown_waits():
    p = run.the_course()
    out = p.notify_learners("A second note about the course.", 999, run.ADMIN)
    assert (out.ran, out.check) == (False, "legal_in_state")
