"""What lands in the record is what the gateway can vouch for.

A number the model wrote as a word goes to repair instead of crashing the check.
A screening is stamped with the guardrail version that gave it, and an answer
from another version, or in a shape nobody asked for, is no answer. A person's
reason for a rejection is what the next draft is told. And the notice to
learners — the one text they read that no model wrote — is screened before it
is sent.
"""
from __future__ import annotations

import copy

from gateway.provider.port import Screener, Verdict
from gateway.provider.recorded import RecordedGenerator
from scenarios import run, walkthrough as w


class Screening(Screener):
    """Allows everything unless told otherwise, as the version it is set to."""
    version = "guard-1"

    def __init__(self, deny=lambda point, content: None, odd_at=None):
        self.deny, self.odd_at = deny, odd_at

    def screen(self, content, modality, point, subject=""):
        denied = self.deny(point, content)
        if denied:
            return Verdict(False, denied, self.version, point)
        # A category that is not a string, at one point: an adapter's bug.
        return Verdict(True, 42 if point == self.odd_at else None, self.version, point)


def _draft(screener=None, **answers):
    recorded = {f"node:{n}": [copy.deepcopy(w.CONTENT[n])] for n in (w.T1, w.T2, w.T3, w.E1)}
    recorded.update(answers)
    generator = RecordedGenerator({"outline": [copy.deepcopy(w.OUTLINE)], **recorded})
    p = run.pipeline(generator=generator, screener=screener or Screening())
    p.submit_brief(copy.deepcopy(w.BRIEF), run.AUTHOR)
    p.draft_outline(run.AUTHOR)
    p.machine.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    return p


def _topics(p):
    for node in (w.T1, w.T2, w.T3):
        p.generate_node(node, run.AUTHOR)
        run.approve(p, node, **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if node == w.T1 else {}))


def _prompts(p, node):
    return [prompt.instructions for task, prompt in p.generator.asked if task == f"node:{node}"]


def test_a_total_written_as_a_word_is_repaired_with_the_path_it_got_wrong():
    worded = copy.deepcopy(w.CONTENT[w.E1]) | {"points_total": "ten"}
    p = _draft(**{f"node:{w.E1}": [worded, copy.deepcopy(w.CONTENT[w.E1])]})
    _topics(p)
    p.generate_node(w.E1, run.AUTHOR)
    assert p.machine.current.nodes[w.E1].state == "Validated"
    assert "points_total: expected an integer" in _prompts(p, w.E1)[1]


def test_a_node_screened_by_the_version_being_replaced_is_not_stamped_as_screened():
    p = _draft()
    m = p.machine
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {1: False}})
    p.generate_node(w.T2, run.AUTHOR)                  # the service still answers as guard-1
    # It is asked again while the budget lasts, and the course stops when it runs out.
    assert m.current.state == "BlockedRecoverable"
    assert w.T2 not in m.current.screened
    assert [s["event"] for s in m.store.steps].count("ServiceUnreachable") == m.store.budget() + 1

    p.screener.version = "guard-2"                     # the rollout reaches the service
    m.fire("BlockedInputFixed", {"actor": run.AUTHOR["id"]})
    p._screen_node(w.T2)
    assert m.current.nodes[w.T2].state == "Validated"
    assert m.current.screened[w.T2]["guardrail_version"] == "guard-2"


def test_a_screening_answered_in_the_wrong_shape_is_asked_again_until_the_budget_ends():
    p = _draft(screener=Screening(odd_at="node-out"))
    m = p.machine
    p.generate_node(w.T2, run.AUTHOR)
    assert m.current.state == "BlockedRecoverable"
    assert [s["event"] for s in m.store.steps].count("ServiceUnreachable") == m.store.budget() + 1


def test_a_title_beside_the_blocks_is_screened():
    harm = "disable the blade guard"
    titled = copy.deepcopy(w.CONTENT[w.T2]) | {"title": harm}
    p = _draft(screener=Screening(deny=lambda point, content: harm in content and "unsafe"),
               **{f"node:{w.T2}": [titled, copy.deepcopy(w.CONTENT[w.T2])]})
    p.generate_node(w.T2, run.AUTHOR)
    assert p.machine.current.nodes[w.T2].state == "Validated"
    assert "refused: unsafe" in _prompts(p, w.T2)[1]


def test_a_persons_reason_for_a_rejection_is_what_the_next_draft_is_told():
    p = _draft(**{f"node:{w.T2}": [copy.deepcopy(w.CONTENT[w.T2])] * 2})
    m = p.machine
    p.generate_node(w.T2, run.AUTHOR)
    m.fire("NodeRejected", {"node": w.T2, "reason": "mention the handle", "actor": run.AUTHOR["id"]})
    p.generate_node(w.T2, run.AUTHOR)
    assert "refused: mention the handle" in _prompts(p, w.T2)[1]
    run.approve(p, w.T2)
    assert m.current.nodes[w.T2].last_refusal is None


def test_a_notice_the_guardrail_refuses_is_not_sent():
    p = run.the_course()
    m = p.machine
    p.screener = Screening(deny=lambda point, content: point == "notice-out" and "unsafe")
    before = len(m.store.steps)
    out = p.notify_learners("A correction nobody should read.", 40, run.ADMIN)
    assert (out.ran, out.check) == (False, "legal_in_state")
    assert len(m.store.steps) == before


def test_a_notice_cannot_be_declared_approved_by_its_sender():
    p = run.the_course()
    out = p.membrane.request("notify_learners", {"notice": "x", "recipients": 1, "notice_approved": True},
                             run.ADMIN, perform=lambda key: {})
    assert out.check == "schema_valid"


def test_an_image_source_that_is_not_a_string_is_repaired_not_crashed_on():
    odd = copy.deepcopy(w.CONTENT[w.T1])
    odd["blocks"][1]["src"] = {"url": "x"}
    p = _draft(**{f"node:{w.T1}": [odd, copy.deepcopy(w.CONTENT[w.T1])]})
    p.generate_node(w.T1, run.AUTHOR)
    assert p.machine.current.nodes[w.T1].state == "Validated"
    assert "src" in _prompts(p, w.T1)[1]
