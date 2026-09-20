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
        if p.machine.current.nodes[node].state == "Validated":
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


def test_a_rule_change_during_outline_review_makes_checked_nodes_wait_not_die():
    p = _ready(nodes=(w.T1, w.T2, w.T3))
    m = p.machine
    m.fire("OutlineRevised", {"outline": copy.deepcopy(m.current.proposal), "actor": run.AUTHOR["id"]})
    assert m.current.state == "OutlineReview"
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {}})
    topics = (w.T1, w.T2, w.T3)
    assert {m.current.nodes[n].state for n in topics} == {"NeedsRevalidation"}
    p.screener.version = "guard-2"
    p.screen_waiting()                                 # the course is not at work: nothing is asked
    m.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    p.screen_waiting()
    assert {m.current.nodes[n].state for n in topics} == {"Validated"}
    assert temporal.check(m.trace()).ok


def test_a_fork_of_a_revision_the_change_did_not_reach_starts_under_the_rules_in_force():
    p = _ready()
    m = p.machine
    run.publish(p)
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {1: False}})
    assert m.store.revisions[1].state == "Published"   # it may keep its stamps while untouched
    m.fire("ReviseRequested", {"revision": 1})
    assert {n.state for n in m.current.nodes.values()} == {"OutputGuardrail"}
    p.screener.version = "guard-2"
    p.screen_waiting()
    _approve_all(p)
    edited = copy.deepcopy(w.CONTENT[w.T2])
    edited["blocks"][0]["text"] = "check every tool for splits before use"
    m.fire("NodeEdited", {"node": w.T2, "content": edited})
    p.screen_node(w.T2)
    _approve_all(p)
    run.publish(p)
    assert m.current.state == "Published"
    assert temporal.check(m.trace()).ok


def test_a_source_removed_from_the_knowledge_base_withdraws_the_live_course_that_cites_it():
    p = _ready()
    m = p.machine
    run.publish(p)
    cited = w.CONTENT[w.T1]["cites"][0]
    for article in m.world.articles:
        article["chunks"] = [c for c in article.get("chunks") or [] if c != cited]
    m.screener = lambda rev, version: ("allow", version)
    m.fire("KBUpdated", {"to": "kb-next", "reaches": {1: True}})
    assert m.store.revisions[1].state == "Withdrawn"


def test_a_notice_waits_for_consent_to_the_learners_it_reaches():
    p = _ready()
    m = p.machine
    m.fire("CourseChecksRequested")
    shown = [{**s, "what_was_shown": {"recipients": 41}} for s in run.SIGNATURES]
    m.fire("ApprovalGranted", {"signatures": shown})
    assert p.membrane.request("publish_revision", {"revision": m.current.id}, run.ADMIN).ran
    assert not p.notify_learners(run.NOTICE, 40, run.ADMIN).ran     # consent was to 41
    m.fire("ApprovalGranted", {"signatures": run.SIGNATURES})     # fresh consent, to the 40 enrolled
    assert m.current.state == "Published"
    assert not p.notify_learners(run.NOTICE, 999, run.ADMIN).ran
    assert p.notify_learners(run.NOTICE, 40, run.ADMIN).ran


def test_a_discarded_draft_does_not_move_when_a_rule_changes():
    p = _ready()
    m = p.machine
    m.fire("DraftDiscarded", {"reason": "starting over", "actor": run.AUTHOR["id"]})
    before = {n: s.state for n, s in m.store.revisions[1].nodes.items()}
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {}})
    assert {n: s.state for n, s in m.store.revisions[1].nodes.items()} == before
