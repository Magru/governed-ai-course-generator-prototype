"""What a caller cannot forge: a signature, a verdict, a lesson, or who acted."""
from __future__ import annotations

import copy

import pytest

from gateway.membrane import Membrane
from machine.refusal import MachineRefused
from scenarios import cassette, run, walkthrough as w
from scenarios.machine_runs import (CONTENT, EXAM, N1, N2, SIGNATURES, machine, node_through,
                                    to_content)

AUTHOR = run.AUTHOR


@pytest.fixture
def gate():
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    return Membrane(m, "mt-course-001")


def _generated(gate):
    assert gate.request("generate_node_content", {"node": N1, "prompt": "p-1"}, AUTHOR,
                        perform=lambda key: {"content": copy.deepcopy(CONTENT[N1])}).ran


def test_a_signature_with_no_signer_does_not_fill_a_role():
    m = machine()
    to_content(m)
    for node in (N1, N2, EXAM):
        node_through(m, node)
        m.fire("NodeApproved", {"node": node, "actor": "author-1"})
    m.fire("CourseChecksRequested")
    assert m.current.state == "PendingApproval"
    forged = [SIGNATURES[0], {"role": "compliance-officer"},
              {"actor": "author-1", "role": "course-author"}]
    with pytest.raises(MachineRefused, match="approval_chain_satisfied"):
        m.fire("ApprovalGranted", {"signatures": forged})


def test_a_request_calling_itself_the_system_is_not_the_gateway(gate):
    _generated(gate)
    impostor = {"id": "gateway", "kind": "system"}
    out = gate.request("admit_to_revision", {"node": N1, "artifact": N1, "screened": "s"},
                       impostor, perform=lambda key: {"verdict": "allow", "guardrail_version": "guard-1"})
    assert (out.ran, out.check) == (False, "policy_allows")


def test_a_call_cannot_hand_back_fields_the_checks_judged(gate):
    with pytest.raises(TypeError):
        gate.request("approve_node", {"node": N1, "what_was_shown": "x"}, AUTHOR,
                     perform=lambda key: {"actor": "admin-1"})
    out = gate.request("generate_node_content", {"node": N1, "prompt": "p-1"}, AUTHOR,
                       perform=lambda key: {"content": copy.deepcopy(CONTENT[N1]), "node": "other"})
    assert out.ran and gate.machine.current.nodes[N1].content == CONTENT[N1]


@pytest.mark.parametrize("answer", ["a lesson", 7, None, ["blocks"]])
def test_an_answer_that_is_not_an_object_is_a_model_error_not_landed(gate, answer):
    out = gate.request("generate_node_content", {"node": N1, "prompt": "p-1"}, AUTHOR,
                       perform=lambda key: {"content": answer})
    assert (out.ran, out.check) == (False, "answer")
    assert gate.machine.current.nodes[N1].content is None


@pytest.mark.parametrize("block", [{"type": "paragraph"}, {"type": "paragraph", "text": "", "cites": ["mt-kb-001"]},
                                   {"type": "paragraph", "text": "a claim", "cites": []}, 1])
def test_a_block_missing_what_the_catalog_says_it_carries_is_refused(block):
    from engines.schema.engine import check_blocks
    world = machine().world
    verdict = check_blocks({"id": N1, "blocks": [block]}, world.block_types, world.block_schemas)
    assert not verdict.ok


def test_the_same_refusal_twice_is_two_repairs_not_already_done():
    leak = cassette.leaking(w.T2)
    generator = cassette.course_generator()
    generator.answers[f"node:{w.T2}"] = [copy.deepcopy(leak), copy.deepcopy(leak),
                                         copy.deepcopy(w.CONTENT[w.T2])]
    screener = cassette.course_screener()
    p = run.pipeline(generator=generator, screener=screener)
    m = p.machine
    p.submit_brief(copy.deepcopy(w.BRIEF), AUTHOR)
    while m.current.state == "OutlineDrafting":
        p.draft_outline(AUTHOR)
    m.fire("OutlineApproved", {"actor": AUTHOR["id"]})
    p.generate_node(w.T2, AUTHOR)
    assert m.current.nodes[w.T2].state == "Validated"
    assert len([a for a in generator.asked if a[0] == f"node:{w.T2}"]) == 3


def test_every_word_a_learner_sees_is_screened():
    from gateway.screened_text import screened_text
    content = {"blocks": [
        {"type": "checklist", "items": ["a refused sentence"]},
        {"type": "quiz", "question": "q", "options": ["an option", "another"], "answer": 0, "points": 1},
        {"type": "image", "src": "x.png", "alt": "alt words", "caption": "c", "cites": ["mt-kb-001"]}]}
    text = screened_text(content)
    for words in ("a refused sentence", "an option", "another", "alt words"):
        assert words in text
    assert "x.png" not in text and "mt-kb-001" not in text
