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


def test_generating_a_node_outside_the_content_phase_is_refused():
    v = engine.check("generate_node", AUTHOR, brief(), "Published", DATA)
    assert not v.ok and v.refusal.detail[0]["rule"] == "state_permits"


def test_a_recovery_the_table_guarantees_is_not_refused():
    """transitions.yaml has BlockedRecoverable --BriefSubmitted--> BriefValidation.
    An earlier version of the policy gated every action on a fixed set of states
    and refused this one — terminally, since a policy refusal ends the revision.
    Which states an action is legal in is the table's question, not the policy's."""
    assert engine.check("submit_brief", AUTHOR, brief(), "BlockedRecoverable", DATA).ok


def test_lesson_length_is_not_asked_here():
    """One owner per question: it is part of satisfiability, and Z3 owns that.
    Asking both meant OPA refused first and terminally, and the unsat core Z3
    exists to produce could never be reached."""
    assert engine.check("submit_brief", AUTHOR, brief(minutes_per_lesson=999),
                        "AwaitingBrief", DATA).ok


ADVERSARIAL = [
    ("an unknown role", {"id": "author-1", "role": "intruder"}, brief(), "AwaitingBrief", DATA),
    ("an unknown actor", {"id": "nobody", "role": "course-author"}, brief(), "AwaitingBrief", DATA),
    ("no node count", AUTHOR, {"audience": ["apprentices"], "minutes_per_lesson": 20},
     "AwaitingBrief", DATA),
    ("no audience", AUTHOR, {"node_count": 3, "minutes_per_lesson": 20}, "AwaitingBrief", DATA),
    ("an empty audience", AUTHOR, brief(audience=[]), "AwaitingBrief", DATA),
    ("no thresholds", AUTHOR, brief(), "AwaitingBrief", {"grants": DATA["grants"], "thresholds": {}}),
    ("an unknown action", AUTHOR, brief(), "AwaitingBrief", DATA),
    ("a node in the wrong phase", AUTHOR, brief(), "Withdrawn", DATA),
]


@pytest.mark.parametrize("label,actor,b,state,data",
                         [(a, b, c, d, e) for a, b, c, d, e in ADVERSARIAL],
                         ids=[a for a, *_ in ADVERSARIAL])
def test_a_refusal_always_names_a_rule(label, actor, b, state, data):
    """The property, rather than one hole in it: wherever the policy says no it
    must say why. An earlier version returned `allow=false` with an empty `deny`
    for seven input classes and Python wrote the reason — which reads to a caller
    as the policy's verdict about a sentence the policy never produced."""
    action = "delete_course" if label == "an unknown action" else "submit_brief"
    if label == "a node in the wrong phase":
        action = "generate_node"
    verdict = engine.check(action, actor, b, state, data)
    if verdict.ok:
        return
    assert verdict.refusal.detail, f"{label}: refused with no rule named"
    assert verdict.refusal.detail[0].get("rule"), f"{label}: a reason with no rule"


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


# ------------------------------------------------- approval_chain_satisfied

APPROVAL_ORG = DATA | {"approval": ORG["approval"]}
FULL_CHAIN = [{"actor": "admin-1", "role": "training-administrator"},
              {"actor": "compliance-1", "role": "compliance-officer"}]


def test_a_complete_signature_chain_is_allowed():
    assert engine.check_approval(1, FULL_CHAIN, APPROVAL_ORG).ok


def test_a_missing_signature_names_the_role_that_is_missing():
    v = engine.check_approval(1, FULL_CHAIN[:1], APPROVAL_ORG)
    assert not v.ok and v.refusal.kind == "named-rule"
    assert any("compliance-officer" in d["message"] for d in v.refusal.detail)
    assert all(d["rule"] == "approval_chain_satisfied" for d in v.refusal.detail)


def test_the_right_number_of_the_wrong_signatures_is_still_refused():
    """Two signatures, neither from compliance. The count clause is satisfied
    and the roles clause is not, which is the case a count-only guard misses."""
    wrong = [{"actor": "admin-1", "role": "training-administrator"},
             {"actor": "author-1", "role": "course-author"}]
    v = engine.check_approval(1, wrong, APPROVAL_ORG)
    assert not v.ok
    assert any("compliance-officer" in d["message"] for d in v.refusal.detail)


def test_an_organisation_that_has_not_said_whose_signatures_cannot_publish():
    """Silence about the approval rule is not consent to publish."""
    v = engine.check_approval(1, FULL_CHAIN, DATA | {"approval": {}})
    assert not v.ok
    assert all(d["rule"] == "approval_chain_satisfied" for d in v.refusal.detail)


def test_an_approval_is_not_refused_for_anything_about_a_brief():
    """The brief-shaped deny clauses had no action guard, so an approval — which
    carries no brief — was refused for not saying how many nodes it wanted."""
    v = engine.check_approval(1, [], APPROVAL_ORG)
    assert not v.ok
    assert not any("node" in d["message"] for d in v.refusal.detail), v.refusal.detail


def test_the_same_refusal_reads_the_same_way_twice():
    """`deny` is a set; an artifact that names a different rule each run is not
    an audit record."""
    runs = [engine.check_approval(1, FULL_CHAIN[:1], APPROVAL_ORG).refusal.summary
            for _ in range(3)]
    assert len(set(runs)) == 1
