"""Permission is OPA's, and it must be OPA that answers."""
import pathlib, shutil, subprocess, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.contract import EngineUnavailable
from engines.opa import engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORG = yaml.safe_load((ROOT / "fixtures" / "organisation.yaml").read_text(encoding="utf-8"))
DATA = {"grants": {p["id"]: {"may_author_for": p["may_author_for"]} for p in ORG["people"]},
        "thresholds": ORG["thresholds"]}
AUTHOR = {"id": "author-1", "role": "course-author"}


def brief(**over):
    base = {"audience": ["apprentices"], "node_count": 3, "minutes_per_lesson": 20}
    return base | over


def test_the_policy_file_is_valid_rego():
    assert subprocess.run(["opa", "check", str(engine.POLICY)]).returncode == 0


def test_an_author_may_write_for_a_granted_audience():
    assert engine.check("submit_brief", AUTHOR, brief(), "AwaitingBrief", DATA).ok


def test_an_audience_they_were_not_granted_is_refused_by_name():
    v = engine.check("submit_brief", AUTHOR, brief(audience=["supervisors"]), "AwaitingBrief", DATA)
    assert not v.ok
    assert v.refusal.kind == "named-rule"
    assert v.refusal.detail[0]["rule"] == "audience_permitted"
    assert "supervisors" in v.refusal.summary


def test_a_threshold_refusal_says_which_number_and_what_the_limit_is():
    v = engine.check("submit_brief", AUTHOR, brief(node_count=99), "AwaitingBrief", DATA)
    assert "99" in v.refusal.summary and "12" in v.refusal.summary


def test_a_state_the_action_is_illegal_in_is_refused():
    v = engine.check("generate_node", AUTHOR, brief(), "Published", DATA)
    assert not v.ok and v.refusal.detail[0]["rule"] == "state_permits"


def test_thresholds_come_from_configuration_not_from_the_policy():
    """Raising the organisation's limit changes the answer without touching Rego."""
    loosened = DATA | {"thresholds": DATA["thresholds"] | {"max_nodes_per_course": 100}}
    assert engine.check("submit_brief", AUTHOR, brief(node_count=99), "AwaitingBrief", loosened).ok


def test_a_missing_binary_raises_rather_than_passing(monkeypatch):
    """The property that makes 'real OPA' provable: there is no Python mirror to
    fall back to, so a missing engine stops the run instead of quietly replacing it."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(EngineUnavailable, match="no Python fallback"):
        engine.check("submit_brief", AUTHOR, brief(), "AwaitingBrief", DATA)
