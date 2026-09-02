"""Coverage, and the property that an engine which did not run must not say yes."""
import pathlib, shutil, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.contract import EngineUnavailable
from engines.prolog import engine

DEVELOPS = {"bench-safety": ["bench-safety"], "tool-inspection": ["tool-inspection"]}
APPROVED = {"id": "mt-node-001", "skill": "bench-safety", "state": "NodeApproved"}
DRAFTED = {"id": "mt-node-002", "skill": "tool-inspection", "state": "Validated"}


def test_an_approved_node_covers_its_objective():
    assert engine.check_coverage("c", ["bench-safety"], [APPROVED], DEVELOPS).ok


def test_teaching_is_not_the_same_as_covering():
    """An unapproved node is work, not coverage — and the reason says so."""
    v = engine.check_coverage("c", ["tool-inspection"], [DRAFTED], DEVELOPS)
    assert not v.ok
    assert v.refusal.detail[0]["reason"] == "taught_but_not_approved"


def test_nothing_teaching_it_reads_differently_from_nobody_approving_it():
    v = engine.check_coverage("c", ["dust-extraction"], [APPROVED], DEVELOPS)
    assert v.refusal.detail[0]["reason"] == "no_node_teaches_it"


def test_a_backslash_no_longer_breaks_the_facts_file():
    """The bug this pair of tests exists for. A value ending in a backslash used
    to escape its own closing quote; swipl then skipped every clause it could not
    read, exited zero, and the empty result was returned as 'nothing is
    uncovered' — a formal engine reporting a pass it never computed. The
    identifier is escaped now, so the question is answered rather than skipped."""
    v = engine.check_coverage("c", ["o1"], [{"id": "n\\", "skill": "s",
                                             "state": "Validated"}], {"s": ["o1"]})
    assert not v.ok, "o1 is covered by nothing approved; this must not pass"
    assert v.refusal.detail[0]["objective"] == "o1"


def test_a_program_swipl_cannot_load_raises_rather_than_passing():
    """And the second half: if swipl does report trouble, that is unavailability,
    never an answer. Verified by pointing the engine at a program that is not
    valid Prolog at all."""
    import unittest.mock
    broken = engine.PROGRAM.parent / "_broken_probe.pl"
    broken.write_text("this is not prolog(\n", encoding="utf-8")
    try:
        with unittest.mock.patch.object(engine, "PROGRAM", broken):
            with pytest.raises(EngineUnavailable):
                engine.check_coverage("c", ["o1"], [APPROVED], DEVELOPS)
    finally:
        broken.unlink()


def test_a_missing_binary_raises(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(EngineUnavailable, match="No Python path"):
        engine.check_coverage("c", ["o"], [], {})
