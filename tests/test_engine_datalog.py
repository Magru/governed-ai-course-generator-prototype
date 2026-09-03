"""Reachability, and the path that makes a refusal actionable.

The engine with the most rules in this project had no test file of its own; its
only exercise was one refusal scene. That is enough to notice it crashing and
not enough to notice it answering.
"""
import pathlib, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.contract import EngineUnavailable
from engines.datalog import engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
KB = yaml.safe_load((ROOT / "fixtures" / "kb.yaml").read_text(encoding="utf-8"))
ARTICLES = KB["articles"]
VISIBILITY = {k: v for k, v in KB["resolved_visibility"].items() if k != "source"}
TWIN = yaml.safe_load((ROOT / "fixtures" / "evil-twins" /
                       "03-restricted-source.yaml").read_text(encoding="utf-8"))

OPEN = [{"id": "n1", "cites": ["mt-kb-001", "mt-kb-002"]}]


def test_a_course_citing_only_open_sources_is_allowed():
    assert engine.check_permission_leak(OPEN, ARTICLES, ["apprentices"], VISIBILITY).ok


def test_the_restricted_source_is_refused():
    v = engine.check_permission_leak(TWIN["brief"]["nodes"], ARTICLES,
                                     TWIN["brief"]["audience"], VISIBILITY)
    assert not v.ok and v.refusal.kind == "leak-path"


def test_the_path_names_all_four_hops():
    """§9 promises node → chunk → article → audience. Three of those tell an
    author to drop a citation; the fourth tells them what document it came out
    of, which is what decides whether the answer is to drop it or to widen the
    audience."""
    v = engine.check_permission_leak(TWIN["brief"]["nodes"], ARTICLES,
                                     TWIN["brief"]["audience"], VISIBILITY)
    for row in v.refusal.detail:
        assert set(row) == {"node", "chunk", "article", "audience"}
        assert all(row.values())


def test_an_audience_that_can_see_nothing_gets_an_answer():
    """The exact case the check exists for.

    pyDatalog will not resolve a negation over a predicate with no clauses, so
    an audience with an empty visibility list raised `Predicate without
    definition: visible/2` instead of reporting that everything leaks.
    """
    v = engine.check_permission_leak(OPEN, ARTICLES, ["newcomers"], {})
    assert not v.ok
    assert {r["chunk"] for r in v.refusal.detail} == {"mt-kb-001", "mt-kb-002"}


def test_a_course_with_no_nodes_is_allowed_rather_than_crashing():
    assert engine.check_permission_leak([], ARTICLES, ["apprentices"], VISIBILITY).ok


def test_a_citation_to_nothing_is_ungrounded_not_a_leak():
    """Two different questions, and an author fixes them differently: a leak
    means drop the citation, an ungrounded claim means the retrieval returned
    something that is not in the base at all."""
    invented = [{"id": "n1", "cites": ["mt-kb-999"]}]
    grounding = engine.check_grounding(invented, ARTICLES)
    assert not grounding.ok and grounding.refusal.kind == "ungrounded-claim"
    leak = engine.check_permission_leak(invented, ARTICLES, ["apprentices"], VISIBILITY)
    assert leak.ok, "a chunk that does not exist cannot be a permission leak"


def test_every_real_citation_is_grounded():
    assert engine.check_grounding(OPEN, ARTICLES).ok


def test_grounding_is_the_engine_it_says_it_is(monkeypatch):
    """It was a list comprehension labelled `engine="datalog"`.

    The answers were right, which is why nothing noticed. A refusal names a
    layer so a reader can go and read the rule that produced it, and a name
    pointing at no rule is the one kind of wrong answer that never shows up as
    a wrong answer.
    """
    def no_datalog():
        raise EngineUnavailable("pyDatalog is not installed")
    monkeypatch.setattr(engine, "pydatalog", no_datalog)
    with pytest.raises(EngineUnavailable):
        engine.check_grounding(OPEN, ARTICLES)
