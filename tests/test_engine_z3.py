"""Satisfiability, and the explanation that makes a refusal actionable."""
import pathlib, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.z3 import engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
TH = yaml.safe_load((ROOT / "fixtures" / "organisation.yaml").read_text(encoding="utf-8"))["thresholds"]
BRIEF = yaml.safe_load((ROOT / "fixtures" / "brief.yaml").read_text(encoding="utf-8"))["brief"]
TWIN = yaml.safe_load((ROOT / "fixtures" / "evil-twins" /
                       "02-contradictory-brief.yaml").read_text(encoding="utf-8"))


def test_a_brief_inside_the_limits_is_satisfiable():
    assert engine.check(BRIEF, TH).ok


def test_the_contradictory_brief_is_refused_with_a_core():
    v = engine.check(TWIN["brief"], TH)
    assert not v.ok and v.refusal.kind == "unsat-core"
    for name in TWIN["expect"]["core_contains"]:
        assert name in v.refusal.detail, f"{name} missing from {v.refusal.detail}"


def test_the_core_is_minimal_not_the_whole_problem():
    """A core that listed every assertion would be no explanation at all."""
    v = engine.check(TWIN["brief"], TH)
    assert len(v.refusal.detail) < 8


def test_an_untracked_assertion_would_be_invisible():
    """Why assert_and_track is used everywhere: z3 can only name what was tracked,
    and an unnamed contradiction sends the author to fix the wrong requirement."""
    import z3
    s = z3.Solver(); s.set(unsat_core=True)
    x = z3.Int("x")
    s.add(x > 10)                                   # untracked on purpose
    s.assert_and_track(x < 5, z3.Bool("tracked_one"))
    assert s.check() == z3.unsat
    assert [str(c) for c in s.unsat_core()] == ["tracked_one"]


def test_a_lesson_of_zero_minutes_is_unsatisfiable():
    v = engine.check(BRIEF | {"minutes_per_lesson": 0}, TH)
    assert not v.ok and "a_lesson_has_positive_length" in v.refusal.detail
