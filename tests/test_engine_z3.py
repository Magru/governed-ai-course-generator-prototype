"""Satisfiability, and the explanation that makes a refusal actionable."""
import pathlib, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.contract import EngineUnavailable
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


def test_each_conflict_names_only_the_requirements_that_collide():
    """Minimality is now per conflict, not over the whole refusal.

    `detail` is the union of the per-group cores, so it grows with the number of
    conflicts and a bound on its length says nothing. What must stay true is
    that each individual conflict names only what actually collides — two
    requirements, here, not the group they came from.
    """
    v = engine.check(TWIN["brief"], TH)
    assert v.refusal.detail == ["max_minutes_per_lesson", "max_nodes_per_course",
                                "minutes_per_lesson", "requested_nodes"]
    for conflict in v.refusal.summary.split("; "):
        assert len(conflict.split(", ")) == 2, conflict


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


# ------------------------------------------------------- every conflict, once

THREE_WAYS_WRONG = {"requested_nodes": 14, "minutes_per_lesson": 40,
                    "audience": ["a", "b", "c", "d", "e"]}


def test_a_brief_breaking_three_limits_is_told_about_three():
    """One solve over every constraint returns one minimal core, which is
    correct and not enough: the author fixes it, resubmits, and is told about
    the second. §9 hands the core over so the fix happens once."""
    v = engine.check(THREE_WAYS_WRONG, TH)
    assert not v.ok
    assert {"max_nodes_per_course", "max_minutes_per_lesson",
            "max_audience_breadth"} <= set(v.refusal.detail)


def test_each_conflict_is_reported_separately_rather_than_as_one_heap():
    v = engine.check(THREE_WAYS_WRONG, TH)
    assert v.refusal.summary.count(";") == 2, v.refusal.summary


def test_no_constraint_links_two_of_the_grouped_variables():
    """The property that makes solving per group both complete and minimal.

    Each core is minimal within its group, and the union is every conflict, only
    because no constraint mentions two of the three variables — a conflict
    cannot then straddle a group boundary. Asked of z3 rather than of the source
    text, so it stays true however the constraints are written.
    """
    from z3.z3util import get_vars
    owner = {"nodes": "requested_nodes", "minutes": "minutes_per_lesson",
             "audience": "audience_breadth"}
    for group, constraints in engine.constraint_groups(BRIEF, TH).items():
        for name, claim in constraints.items():
            mentioned = {str(v) for v in get_vars(claim)}
            assert mentioned <= {owner[group]}, (
                f"{name} in the {group} group mentions "
                f"{sorted(mentioned - {owner[group]})}, so its core is no longer "
                f"minimal and a conflict can straddle two groups")


def test_the_grouping_leaves_no_constraint_behind():
    """A partition, not a selection. A constraint dropped while regrouping is a
    requirement that silently stops being checked."""
    # A brief that states its count *and* lists its nodes, so every constraint
    # this engine can raise is present at once.
    groups = engine.constraint_groups(BRIEF | {"requested_nodes": 3}, TH)
    names = [n for constraints in groups.values() for n in constraints]
    assert len(names) == len(set(names)), "a constraint is in two groups"
    assert set(names) == {
        "requested_nodes", "nodes_the_brief_lists", "max_nodes_per_course",
        "a_course_has_at_least_one_node", "minutes_per_lesson",
        "max_minutes_per_lesson", "a_lesson_has_positive_length",
        "audience_breadth", "max_audience_breadth"}


def test_an_absent_solver_is_unavailable_rather_than_a_pass(monkeypatch):
    """The refactor moved the import into two helpers. A layer that cannot run
    must say so; the one thing it may never do is answer."""
    import builtins
    real = builtins.__import__

    def no_z3(name, *args, **kwargs):
        if name == "z3":
            raise ImportError("no z3 here")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_z3)
    with pytest.raises(EngineUnavailable):
        engine.check(BRIEF, TH)
    with pytest.raises(EngineUnavailable):
        engine.check_arithmetic({"id": "n", "blocks": [1], "minutes": 5}, TH)
