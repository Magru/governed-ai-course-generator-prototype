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


def test_the_brief_is_judged_with_the_nodes_it_lists():
    """The happy brief states no count and lists three nodes.

    It was checked as a two-node brief, because the count was filled in from the
    number of objectives when the field was absent. Both numbers were inside the
    limit, so the layer went on saying yes to a brief nobody submitted.
    """
    assert engine.check(BRIEF, TH).facts["nodes"] == len(BRIEF["nodes"])


def test_a_brief_that_does_not_say_how_long_a_lesson_runs_is_not_read_as_zero():
    silent = {k: v for k, v in BRIEF.items() if k != "minutes_per_lesson"}
    v = engine.check(silent, TH)
    assert not v.ok and v.refusal.kind == "unstated-requirement"
    assert "how long a lesson runs" in v.refusal.summary
    assert "a_lesson_has_positive_length" not in str(v.refusal.detail), (
        "the brief was silent and the refusal blamed it for asking for zero")


def test_a_brief_that_contradicts_itself_has_both_statements_named():
    """Four nodes asked for, three listed. Python used to pick one silently."""
    v = engine.check(BRIEF | {"requested_nodes": 4}, TH)
    assert not v.ok and v.refusal.kind == "unsat-core"
    assert {"requested_nodes", "nodes_the_brief_lists"} <= set(v.refusal.detail)


def test_a_count_of_zero_is_an_answer_and_not_an_absence():
    """`or` treated 0 as unset. A brief asking for no nodes is asking for
    something the model forbids, and it must be refused for that."""
    v = engine.check({k: v for k, v in BRIEF.items() if k != "nodes"}
                     | {"requested_nodes": 0}, TH)
    assert not v.ok and "a_course_has_at_least_one_node" in v.refusal.detail


def test_an_organisation_with_no_limits_gets_no_verdict():
    v = engine.check(BRIEF, {})
    assert not v.ok and v.refusal.kind == "unstated-requirement"
    assert "max_nodes_per_course" in v.refusal.summary


# ------------------------------------------------------ arithmetic_consistent

ARITH_TH = TH | {"minutes_per_block": 5}


def test_an_exam_whose_points_add_up_is_allowed():
    exam = {"id": "n3", "questions": [{"points": 4}, {"points": 6}], "points_total": 10}
    assert engine.check_arithmetic(exam, ARITH_TH).ok


def test_an_exam_whose_points_do_not_reach_the_stated_maximum_names_both_sums():
    """§4 says the refusal is "the failing sum". Naming only the total tells an
    author the total is wrong; naming both tells them which of the two to move."""
    exam = {"id": "n3", "questions": [{"points": 4}, {"points": 5}], "points_total": 10}
    v = engine.check_arithmetic(exam, ARITH_TH)
    assert not v.ok and v.refusal.kind == "failing-sum"
    assert set(v.refusal.detail["core"]) == {"points_sum_to_the_total",
                                             "points_total_is_as_stated"}


def test_a_duration_that_does_not_match_the_block_count_is_refused():
    v = engine.check_arithmetic({"id": "n1", "blocks": [1, 2, 3], "minutes": 20}, ARITH_TH)
    assert not v.ok and "duration_matches_the_block_count" in v.refusal.detail["core"]


def test_a_node_with_no_numbers_in_it_has_nothing_to_check():
    assert engine.check_arithmetic({"id": "n2"}, ARITH_TH).ok


def test_half_a_statement_is_refused_rather_than_passed():
    """Questions and no stated total. Reading the absent total as zero would
    refuse for the wrong reason; reading it as "no claim" would pass an exam
    nobody can mark."""
    v = engine.check_arithmetic({"id": "n3", "questions": [{"points": 4}]}, ARITH_TH)
    assert not v.ok and v.refusal.kind == "unstated-requirement"
