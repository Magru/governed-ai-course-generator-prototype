"""Five guards about the shape of a course, each refusing with what §4 promises.

All five were named in `guards.yaml` and implemented nowhere, which is the
quietest kind of gap: the glossary says Datalog owns the question, a reader
believes the question is answered, and nothing anywhere asks it.
"""
import pathlib, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.datalog import structure as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
TWIN = yaml.safe_load((ROOT / "fixtures" / "evil-twins" /
                       "04-exam-before-material.yaml").read_text(encoding="utf-8"))
CATALOG = yaml.safe_load((ROOT / "fixtures" / "namespace.yaml")
                         .read_text(encoding="utf-8"))["skills"]

COURSE = [{"id": "n1", "skill": "bench-safety"},
          {"id": "n2", "skill": "tool-inspection", "requires": ["n1"]},
          {"id": "n3", "type": "exam", "topics": ["n1", "n2"], "requires": ["n2"]}]
OUTLINE = ["n1", "n2", "n3"]


# ------------------------------------------------------------ skills_grounded

def test_a_skill_the_catalog_has_is_grounded():
    assert S.check_skills_grounded(COURSE, ["bench-safety", "tool-inspection"]).ok


def test_an_invented_skill_is_named():
    v = S.check_skills_grounded(COURSE + [{"id": "n4", "skill": "sword-fighting"}],
                                ["bench-safety", "tool-inspection"])
    assert not v.ok and v.refusal.kind == "invented-skill"
    assert "sword-fighting" in v.refusal.summary


def test_the_real_catalog_grounds_the_real_skills():
    """Against the fixture's own catalog rather than a list written here."""
    assert S.check_skills_grounded(
        [{"id": "n1", "skill": CATALOG[0]}], CATALOG).ok


# ----------------------------------------------------------- references_live

def test_a_reference_into_the_outline_is_live():
    assert S.check_references_live(
        COURSE + [{"id": "n5", "refers_to": ["n1"]}], OUTLINE, "v3").ok


def test_a_dead_reference_names_the_outline_that_dropped_its_target():
    """§4: "naming the reference and the outline version that dropped its
    target". The version is the part an author cannot work out alone — the
    reference was live when it was written."""
    v = S.check_references_live([{"id": "n5", "refers_to": ["n9"]}], OUTLINE, "v3")
    assert not v.ok and v.refusal.kind == "dead-reference"
    assert v.refusal.detail[0]["outline_version"] == "v3"
    assert "v3" in v.refusal.summary


# ---------------------------------------------------------- ordering_acyclic

def test_a_course_whose_prerequisites_run_backwards_is_allowed():
    assert S.check_ordering_acyclic(COURSE).ok


def test_a_cycle_is_found_rather_than_hung_on():
    """The reason the transitive closure is written left-recursive.

    Written the other way round — logically the same rule — pyDatalog never
    returns on a graph with a cycle, so the guard would hang on the only input
    it exists to catch. This test is the one that would never finish.
    """
    cyclic = [{"id": "a", "requires": ["b"]},
              {"id": "b", "requires": ["c"]},
              {"id": "c", "requires": ["a"]}]
    v = S.check_ordering_acyclic(cyclic)
    assert not v.ok and v.refusal.kind == "prerequisite-cycle"
    assert set(v.refusal.detail["cycle"]) == {"a", "b", "c"}


def test_a_lesson_placed_before_what_it_requires_is_a_different_refusal():
    """A cycle has no resolution but an edit; an order conflict is fixed by
    moving a lesson. Same guard, two artifacts."""
    v = S.check_ordering_acyclic([{"id": "a", "requires": ["b"]}, {"id": "b"}])
    assert not v.ok and v.refusal.kind == "ordering-conflict"
    assert v.refusal.detail["out_of_order"] == [{"node": "a", "requires": "b"}]


def test_the_seeded_row_is_not_reported_as_a_cycle():
    """A negated relation has to be seeded so it resolves. Seeding a *recursive*
    one made it join with itself, and a course with no prerequisites at all came
    back with a cycle in it."""
    v = S.check_ordering_acyclic([{"id": "n1"}, {"id": "n2"}])
    assert v.ok, v.refusal.summary if not v.ok else ""


# ------------------------------------------------------- content_approved

def test_an_exam_over_approved_topics_may_be_generated():
    assert S.check_content_approved(COURSE, OUTLINE, ["n1", "n2"]).ok


def test_the_twin_generating_an_exam_before_its_material_is_refused():
    nodes = TWIN["brief"]["nodes"]
    outline = [n["id"] for n in nodes]
    approved = [n["id"] for n in nodes if n.get("state") == "NodeApproved"]
    v = S.check_content_approved(nodes, outline, approved)
    assert not v.ok
    assert v.refusal.kind == TWIN["expect"]["artifact"]
    assert v.refusal.engine == TWIN["expect"]["refused_by"]
    assert "mt-node-105" in v.refusal.summary


def test_a_topic_dropped_from_the_outline_stops_being_a_precondition():
    """The reason this guard is Datalog's and not the state store's.

    Quantified over the committed outline, a removed topic is simply no longer
    required. Quantified over the exam's own list, it becomes a precondition
    that can never be met and the exam waits forever.
    """
    assert S.check_content_approved(COURSE, ["n1", "n3"], ["n1"]).ok


# -------------------------------------------------------------- the cascade

def test_the_cascade_reaches_through_an_intermediate_node():
    """n3 requires n2 requires n1. Editing n1 must reach n3, or a course goes
    live with a node built on material that has since changed."""
    assert S.cascade(COURSE, "n1") == ["n2", "n3"]


def test_the_cascade_of_an_untouched_leaf_is_empty():
    assert S.cascade(COURSE, "n3") == []
