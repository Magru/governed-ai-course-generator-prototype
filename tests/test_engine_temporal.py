"""Fifteen properties, each with a trace that breaks it.

A checker nobody has watched fail is a checker nobody knows works, so every
invariant here is paired with a run the specification forbids.
"""
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.temporal import engine
from engines.temporal.invariants import REGISTRY


def test_every_declared_invariant_is_implemented():
    """Nothing in the model may go unchecked."""
    missing = set(engine.declared()) - set(REGISTRY)
    assert not missing, f"the specification states {sorted(missing)} and nothing checks them"


def test_nothing_is_checked_that_the_model_does_not_state():
    extra = set(REGISTRY) - set(engine.declared())
    assert not extra, f"{sorted(extra)} is checked here and stated nowhere"


@pytest.mark.parametrize("ident", sorted(REGISTRY, key=lambda x: int(x[1:])))
def test_the_formula_is_the_specifications_word_for_word(ident):
    assert REGISTRY[ident][0] == engine.declared()[ident]


def test_a_clean_trace_passes():
    trace = [{"event": "BriefSubmitted", "course_state": "BriefValidation"},
             {"event": "OutlineApproved", "course_state": "ContentInProgress"}]
    assert engine.check(trace).ok


VIOLATIONS = {
    "I1": [{"event": "NodeGenerated", "course_state": "Published"}],
    "I2": [{"event": "NodeGenerated", "node_type": "exam", "topics": ["t1"]}],
    "I3": [{"event": "PublishRequested", "course_state": "Published", "stale_nodes": ["n1"]}],
    "I4": [{"event": "NodeEdited", "node": "n1"}, {"event": "Next", "needs_revalidation": []}],
    "I5": [{"event": "OutlineApproved", "removed_nodes": ["n1"]}],
    "I6": [{"event": "NodeGenerated", "node": "n1"}],
    "I7": [{"event": "PolicyChanged", "course_state": "Published",
            "policy_version": "v7", "current_policy_version": "v8", "affected": True}],
    "I8": [{"event": "NodeApproved", "used_restricted": ["n1"]}],
    "I9": [{"event": "ActionTaken", "action": "publish"}],
    "I10": [{"event": "PublishRequested", "course_state": "Published", "revision": 1},
            {"event": "NodeEdited", "revision": 1}],
    "I11": [{"event": "LivePointerMoved", "live_pointer": 2,
             "revision_states": {2: "Withdrawn"}}],
    "I12": [{"event": "LivePointerMoved", "superseded": [1]}],
    "I13": [{"event": "RollbackRequested", "rolled_back_to": 1}],
    "I14": [{"event": "Timeout", "held_nodes": ["n1"], "course_state": "ContentInProgress"}],
    "I15": [{"event": "GuardrailChanged", "course_state": "Published",
             "guardrail_version": "g3", "current_guardrail_version": "g4", "affected": True}],
}


@pytest.mark.parametrize("ident", sorted(VIOLATIONS, key=lambda x: int(x[1:])))
def test_each_invariant_catches_a_run_that_breaks_it(ident):
    verdict = engine.check(VIOLATIONS[ident])
    assert not verdict.ok, f"{ident} accepted a trace the specification forbids"
    assert any(v["invariant"] == ident for v in verdict.refusal.detail), (
        f"the trace was refused, but not by {ident}: "
        f"{[v['invariant'] for v in verdict.refusal.detail]}")


def test_the_refusal_names_the_formula_and_the_step():
    v = engine.check(VIOLATIONS["I10"])
    first = v.refusal.detail[0]
    assert first["formula"] and first["event"] and isinstance(first["step"], int)
