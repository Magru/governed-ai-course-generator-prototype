"""An exam is written only over topics that stand approved — at every step, not
only at the first request.

A topic can lose its approval while its exam is being drafted: an author edits
it in another session, or a repair lands. The exam goes back to NodeRepair to
wait, the answer on its way does not land, and waiting costs it no retry. An
exam with no retries left whose topic is still in repair can be released by a
person and goes on waiting; before, releasing it blocked the course again.
"""
from __future__ import annotations

import copy

import pytest

from engines.temporal import engine as temporal
from gateway.provider.port import Screener, Verdict
from gateway.provider.recorded import RecordedGenerator
from machine.refusal import MachineRefused
from scenarios import run, walkthrough as w


class AllowAll(Screener):
    version = "guard-1"

    def screen(self, content, modality, point, subject=""):
        return Verdict(True, None, self.version, point)


def _draft(generator=None):
    """Outline approved, the three topics generated and approved."""
    answers = {f"node:{n}": [copy.deepcopy(w.CONTENT[n])] for n in (w.T1, w.T2, w.T3, w.E1)}
    p = run.pipeline(generator=generator or RecordedGenerator(
        {"outline": [copy.deepcopy(w.OUTLINE)], **answers}), screener=AllowAll())
    p.submit_brief(copy.deepcopy(w.BRIEF), run.AUTHOR)
    p.draft_outline(run.AUTHOR)
    p.machine.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    for node in (w.T1, w.T2, w.T3):
        p.generate_node(node, run.AUTHOR)
        run.approve(p, node, **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if node == w.T1 else {}))
    return p


def _edited(node, text="keep the bench clear, always"):
    content = copy.deepcopy(w.CONTENT[node])
    content["blocks"][0]["text"] = text
    return content


def _land(m, node, key):
    m.fire("NodeGenerated", {"node": node, "content": copy.deepcopy(w.CONTENT[node]),
                             "idempotency_key": key})
    m.fire("GuardrailVerdict", {"node": node, "verdict": "allow"})


def test_a_topic_edited_while_its_exam_is_drafted_sends_the_exam_back_to_wait():
    p = _draft()
    m = p.machine
    m.fire("NodeGenerationRequested", {"node": w.E1, "actor": run.AUTHOR["id"]})
    m.fire("NodeEdited", {"node": w.T1, "content": _edited(w.T1)})
    exam = m.current.nodes[w.E1]
    assert (exam.state, exam.repair_count) == ("NodeRepair", 0)
    with pytest.raises(MachineRefused):
        m.fire("NodeGenerated", {"node": w.E1, "content": copy.deepcopy(w.CONTENT[w.E1]),
                                 "idempotency_key": "late"})
    m.fire("GuardrailVerdict", {"node": w.T1, "verdict": "allow"})
    run.approve(p, w.T1, visuals_reviewed=[f"{w.T1}.blocks[1]"])
    exam = m.current.nodes[w.E1]            # a refused event restores the store
    assert (exam.state, exam.repair_count) == ("ContentDrafting", 0)    # waiting cost nothing
    assert temporal.check(m.trace()).ok


def test_an_answer_that_arrives_after_its_topic_was_edited_does_not_land_through_the_gateway():
    holder = {}

    class EditsMidCall(RecordedGenerator):
        def generate(self, prompt, schema):
            if prompt.instructions.startswith(f"node:{w.E1}"):
                holder["m"].fire("NodeEdited", {"node": w.T1, "content": _edited(w.T1)})
            return super().generate(prompt, schema)

    answers = {f"node:{n}": [copy.deepcopy(w.CONTENT[n])] for n in (w.T1, w.T2, w.T3, w.E1)}
    p = _draft(EditsMidCall({"outline": [copy.deepcopy(w.OUTLINE)], **answers}))
    holder["m"] = m = p.machine
    p.generate_node(w.E1, run.AUTHOR)
    assert m.current.nodes[w.E1].state == "NodeRepair"
    assert p.stages[-1][3] == "not landed: NodeRepair"
    assert temporal.check(m.trace()).ok


def test_an_exam_with_no_retries_left_is_released_to_wait_for_a_topic_in_repair():
    p = _draft()
    m = p.machine
    p.generate_node(w.E1, run.AUTHOR)
    for i in range(m.store.budget()):
        m.fire("NodeRejected", {"node": w.E1, "reason": f"ambiguous {i}", "actor": run.AUTHOR["id"]})
        _land(m, w.E1, f"exam-{i}")
    m.fire("NodeEdited", {"node": w.T2, "content": _edited(w.T2, "wording to repair")})
    m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "deny", "category": "unsafe"})
    m.fire("NodeRejected", {"node": w.E1, "reason": "still ambiguous", "actor": run.AUTHOR["id"]})
    assert m.current.state == "BlockedRecoverable"

    m.fire("BlockedInputFixed", {"actor": run.AUTHOR["id"]})
    exam = m.current.nodes[w.E1]
    assert m.current.state == "ContentInProgress"
    assert (exam.state, exam.repair_count) == ("NodeRepair", 0)
    _land(m, w.T2, "t2-repaired")
    run.approve(p, w.T2)
    assert exam.state == "ContentDrafting"
    assert temporal.check(m.trace()).ok


def test_an_exam_whose_last_attempt_was_in_flight_waits_without_blocking_the_course():
    p = _draft()
    m = p.machine
    m.fire("NodeGenerationRequested", {"node": w.E1, "actor": run.AUTHOR["id"]})
    for _ in range(m.store.budget()):
        m.fire("ModelError", {"node": w.E1})
    assert (m.current.nodes[w.E1].state, m.current.nodes[w.E1].repair_count) == ("ContentDrafting", 2)
    m.fire("NodeEdited", {"node": w.T1, "content": _edited(w.T1)})
    assert m.current.state == "ContentInProgress"
    assert m.current.nodes[w.E1].state == "NodeRepair"
    m.fire("GuardrailVerdict", {"node": w.T1, "verdict": "allow"})
    run.approve(p, w.T1, visuals_reviewed=[f"{w.T1}.blocks[1]"])
    assert m.current.nodes[w.E1].state == "ContentDrafting"
    assert temporal.check(m.trace()).ok
