"""Step one of the membrane, and the layer that was not there.

Everything downstream assumes it ran. Z3 reads minutes as a number; Datalog
reads a node's topics as a list of ids. A model returning a string where an
integer belongs reaches an engine that either crashes or coerces it and answers
confidently about the coercion.
"""
import pathlib, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.contract import EngineUnavailable
from engines.schema import engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIEF = yaml.safe_load((ROOT / "fixtures" / "brief.yaml").read_text(encoding="utf-8"))["brief"]
BLOCK_TYPES = yaml.safe_load((ROOT / "fixtures" / "namespace.yaml")
                             .read_text(encoding="utf-8"))["block_types"]


def test_the_real_brief_has_the_shape_it_must_have():
    assert engine.check(BRIEF, "brief").ok


def test_the_real_outline_has_the_shape_it_must_have():
    assert engine.check({"nodes": BRIEF["nodes"]}, "outline").ok


def test_a_wrong_type_is_refused_with_the_path_and_the_type():
    """§4: "the failing path and the expected type". "The brief is invalid"
    sends an author to read the whole thing."""
    v = engine.check(BRIEF | {"minutes_per_lesson": "twenty"}, "brief")
    assert not v.ok and v.refusal.kind == "failing-path"
    assert v.refusal.detail[0]["path"] == "brief.minutes_per_lesson"
    assert "integer" in v.refusal.detail[0]["expected"]


def test_the_path_reaches_inside_a_list():
    v = engine.check(BRIEF | {"audience": ["apprentices", 4]}, "brief")
    assert v.refusal.detail[0]["path"] == "brief.audience[1]"


def test_a_missing_required_field_is_refused():
    v = engine.check({k: x for k, x in BRIEF.items() if k != "title"}, "brief")
    assert not v.ok and "title" in v.refusal.detail[0]["message"]


def test_every_failure_is_reported_not_only_the_first():
    """An author fixing one field at a time and resubmitting each time is the
    same waste the z3 core enumeration exists to avoid."""
    v = engine.check(BRIEF | {"minutes_per_lesson": "twenty", "audience": []}, "brief")
    assert len(v.refusal.detail) >= 2


def test_a_block_is_checked_against_the_organisations_own_types():
    assert engine.check({"type": "heading", "text": "Bench safety"}, "block",
                        block_types=BLOCK_TYPES).ok
    v = engine.check({"type": "sonnet"}, "block", block_types=BLOCK_TYPES)
    assert not v.ok and "heading" in v.refusal.detail[0]["expected"]


def test_a_block_with_no_type_list_is_refused_rather_than_guessed():
    """Which blocks exist is the organisation's decision. Falling back to a list
    written in this package would validate against a second opinion."""
    v = engine.check({"type": "heading"}, "block")
    assert not v.ok and v.refusal.kind == "unstated-requirement"


def test_an_unknown_shape_is_unavailable_rather_than_allowed():
    with pytest.raises(EngineUnavailable):
        engine.check({}, "invoice")


@pytest.mark.parametrize("block", [
    {"type": "paragraph", "text": " ", "cites": ["mt-kb-001"]},
    {"type": "paragraph", "text": "​", "cites": ["mt-kb-001"]},
    {"type": "checklist", "items": ["\u200b"]},
    {"type": "quiz", "question": "q", "options": ["same", "same"], "answer": 0, "points": 1},
    {"type": "quiz", "question": "q", "options": ["a", "b"], "answer": 2, "points": 1},
])
def test_a_block_that_shows_a_learner_nothing_or_cannot_be_answered_is_refused(block):
    from machine.world import load
    world = load()
    assert not engine.check_blocks({"id": "n", "blocks": [block]}, world.block_types,
                                   world.block_schemas).ok


def test_a_refusal_names_the_rule_that_failed_not_the_first_one_present():
    from machine.world import load
    world = load()
    v = engine.check_blocks({"id": "n", "blocks": [{"type": "heading", "text": ""}]},
                            world.block_types, world.block_schemas)
    assert v.refusal.detail[0]["expected"] == "minLength: 1"


def test_a_block_carries_only_what_its_catalog_row_defines():
    from machine.world import load
    world = load()
    extra = {"type": "paragraph", "text": "clean", "src": "anything at all", "cites": ["mt-kb-001"]}
    assert not engine.check_blocks({"id": "n", "blocks": [extra]}, world.block_types,
                                   world.block_schemas).ok


@pytest.mark.parametrize("options", [["<", "=", ">"], ["—", "✓"], ["==", "!="]])
def test_an_answer_option_needs_a_visible_character_not_a_letter(options):
    from machine.world import load
    world = load()
    quiz = {"type": "quiz", "question": "which is it?", "options": options, "answer": 0, "points": 1}
    assert engine.check_blocks({"id": "n", "blocks": [quiz]}, world.block_types,
                               world.block_schemas).ok
