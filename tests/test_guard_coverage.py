"""Every guard the glossary gives an engine is answered, or says why not.

The count is derived from the model rather than written down, so it cannot go
stale — and a guard added to `guards.yaml` fails this suite the moment it is
added, which is the point.
"""
import pathlib, sys
import pytest, yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.registry import IMPLEMENTED, PARTIAL

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUARDS = yaml.safe_load((ROOT / "model" / "guards.yaml").read_text(encoding="utf-8"))["guards"]

#: Owners this package does not answer for. The state store is the running
#: system; a person is a person; a catalog rule belongs to the platform.
#: "Catalog schema" is ours after all: the catalog decides what a block may be,
#: and this package validates against the list the organisation publishes. It sat
#: here while `engines/schema` validated blocks anyway, so the registry's
#: two-direction check passed only because the guard name never came up.
NOT_OURS = {"State store", "Human", "Catalog flag · Human", "unstated", "—"}
ENGINE_GUARDS = {g["name"]: g["owner"] for g in GUARDS if g["owner"] not in NOT_OURS}


def test_every_engine_guard_is_implemented_or_declared_partial():
    unanswered = set(ENGINE_GUARDS) - set(IMPLEMENTED) - set(PARTIAL)
    assert not unanswered, (
        f"the glossary gives these to an engine and nothing here answers them: "
        f"{sorted(unanswered)}")


def test_nothing_is_registered_that_the_model_does_not_name():
    stray = (set(IMPLEMENTED) | set(PARTIAL)) - set(ENGINE_GUARDS)
    assert not stray, f"{sorted(stray)} is registered here and named in no glossary entry"


def test_a_partial_guard_says_which_share_is_missing():
    for name, reason in PARTIAL.items():
        assert len(reason) > 60, f"{name} is marked partial with no explanation"


def test_a_guard_is_not_both_implemented_and_partial():
    assert not set(IMPLEMENTED) & set(PARTIAL)


@pytest.mark.parametrize("name", sorted(IMPLEMENTED))
def test_each_registered_guard_points_at_something_callable(name):
    assert callable(IMPLEMENTED[name])


def test_the_partial_guards_are_the_ones_owned_jointly_or_by_a_service():
    """A guard is partial because of who owns it, not because time ran out.

    Each of these names a layer this phase does not have — the managed guardrail
    or the running state store. If one ever appears here whose owner is Datalog
    alone, that is unfinished work wearing an ownership excuse.
    """
    for name in PARTIAL:
        owner = ENGINE_GUARDS[name]
        assert "·" in owner or owner == "Managed guardrail", (
            f"{name} is owned by {owner} alone and cannot be partial by ownership")
