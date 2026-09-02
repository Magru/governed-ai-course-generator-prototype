"""Each refusal fixture claims a guard and a layer. Both must be the
specification's, not ours.

Checked against guards.yaml, which attributes each guard to one owner. An
earlier version of this test read the transition table's Layer column instead
and passed a deliberately wrong attribution: that column lists everything that
runs at a transition, so "State store" was found in a row whose guard belongs
to Datalog. A test that cannot fail is worth less than no test.

Five of the seven were wrong when they were first written — an exam ahead of its
material was attributed to the state store when the model gives it to Datalog, a
stale node at publication to the temporal layer when publication is guarded by
the state store. Prose review had not caught it; comparing against the vendored
model does.
"""
import pathlib, re, sys
import pytest, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TWINS = sorted((ROOT / "fixtures" / "evil-twins").glob("*.yaml"))
GUARDS = {g["name"]: g for g in
          yaml.safe_load((ROOT / "model" / "guards.yaml").read_text(encoding="utf-8"))["guards"]}
INVENTORY = yaml.safe_load((ROOT / "model" / "state-inventory.yaml").read_text(encoding="utf-8"))
STATES = {v for var in INVENTORY["variables"]
          for v in (var.get("valid_values") or []) if isinstance(v, str)}

# Refusals the model does not express as a transition guard: the gateway's own
# membrane, and the prompt architecture, which is a property of how a prompt is
# built rather than a row in a table.
OUTSIDE_THE_TABLE = {"registered(name)": "Gateway", None: "Prompt architecture"}


@pytest.mark.parametrize("path", TWINS, ids=lambda p: p.stem)
def test_the_guard_it_names_exists(path):
    expect = yaml.safe_load(path.read_text(encoding="utf-8"))["expect"]
    guard = expect.get("guard")
    if guard in OUTSIDE_THE_TABLE:
        assert expect["layer"] == OUTSIDE_THE_TABLE[guard]
        return
    assert guard in GUARDS, (
        f"{guard!r} is not a guard the specification declares. "
        f"Names carry their parameters: {sorted(GUARDS)[:3]} …")


@pytest.mark.parametrize("path", TWINS, ids=lambda p: p.stem)
def test_the_layer_it_names_is_the_one_the_model_gives_that_guard(path):
    expect = yaml.safe_load(path.read_text(encoding="utf-8"))["expect"]
    guard = expect.get("guard")
    if guard in OUTSIDE_THE_TABLE:
        return
    owner = GUARDS[guard]["owner"]
    assert expect["layer"] == owner, (
        f"{path.stem}: claims {expect['layer']!r}; the specification gives "
        f"{guard} to {owner!r}")


@pytest.mark.parametrize("path", TWINS, ids=lambda p: p.stem)
def test_the_end_state_is_a_real_state(path):
    expect = yaml.safe_load(path.read_text(encoding="utf-8"))["expect"]
    ends = expect.get("ends")
    if ends in (None, "refused"):
        return
    assert ends in STATES, f"{ends!r} is not a state either machine declares"


def test_every_layer_that_can_refuse_has_a_twin():
    """A layer with no fixture is a refusal nobody will demonstrate."""
    claimed = {yaml.safe_load(p.read_text(encoding="utf-8"))["expect"]["refused_by"]
               for p in TWINS}
    for layer in ("guardrail", "z3", "datalog", "state-store", "registry"):
        assert layer in claimed, f"no fixture exercises a refusal by {layer}"
