"""The contract is the thing all five engines share, so it is worth its own test."""
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.contract import EngineUnavailable, RefusalWithoutArtifact, Verdict, allowed, refused


def test_a_bare_refusal_is_rejected():
    """A layer that returns false without an artifact has failed, not refused."""
    with pytest.raises(RefusalWithoutArtifact):
        Verdict(ok=False)


def test_a_refusal_carries_something_to_act_on():
    v = refused("unsat-core", "two requirements cannot hold together",
                detail=["requested_nodes", "max_nodes_per_course"], engine="z3")
    assert not v.ok and v.refusal.detail and str(v.refusal).startswith("z3:")


def test_unavailability_is_not_a_pass():
    """There is no value an engine can return to mean 'I could not run'."""
    assert issubclass(EngineUnavailable, Exception)
    assert not hasattr(Verdict, "unknown")
