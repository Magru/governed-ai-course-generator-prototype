"""Fifteen properties, each broken by changing one field of a run that works.

The suite has a spine: `legal_run()` walks a course from brief to publication
and every invariant must let it through. Each negative test is that run with a
single field altered.

The earlier version of this file had no spine. Every property was tested against
a bespoke two-step trace built to fail, so a walk could refuse every legal run in
existence and still show fifteen green ticks — four of them did.
"""
import pathlib, sys
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.temporal import engine, trace as T
from engines.temporal.invariants import REGISTRY
from scenarios.legal_run import (EXAM, LEGAL, N1, N2, find, legal_removal,
                                legal_rollback, legal_run, mutate)


# ------------------------------------------------ the model and the checks

def test_every_declared_invariant_is_implemented():
    missing = set(engine.declared()) - set(REGISTRY)
    assert not missing, f"the specification states {sorted(missing)} and nothing checks them"


def test_nothing_is_checked_that_the_model_does_not_state():
    extra = set(REGISTRY) - set(engine.declared())
    assert not extra, f"{sorted(extra)} is checked here and stated nowhere"


@pytest.mark.parametrize("ident", sorted(REGISTRY, key=lambda x: int(x[1:])))
def test_the_formula_is_the_specifications_word_for_word(ident):
    assert REGISTRY[ident][0] == engine.declared()[ident]


# --------------------------------------------------- the checks and the schema

ENGINE_DIR = pathlib.Path(__file__).resolve().parents[1] / "engines" / "temporal"
SOURCE = "\n".join((ENGINE_DIR / f).read_text(encoding="utf-8")
                   for f in ("invariants.py", "trace.py"))


def _fields_the_checks_read() -> set[str]:
    import re
    return set(re.findall(r'\.(?:state|maybe)\(\s*"([a-z_]+)"', SOURCE))


def test_no_check_reads_a_fact_the_schema_does_not_declare():
    """The root cause of every drift in this file: a check reading something
    nobody promised to record."""
    undeclared = _fields_the_checks_read() - T.STATE_FIELDS - T.PAYLOAD_FIELDS
    assert not undeclared, (f"{sorted(undeclared)} is read here and declared in "
                            f"neither state_fields nor payload_fields")


def _fields_actually_requested() -> set[str]:
    """Every field the walks ask for while checking every run this suite has.

    Watched at the boundary rather than read off the source, because two of the
    version fields are reached through a computed name — a regex calls those
    dead, and the schema's own `read_by` is a claim rather than a fact. This is
    the fact.
    """
    seen: set[str] = set()
    real_state, real_maybe = T.Step.state, T.Step.maybe

    def state(self, field, ident):
        seen.add(field)
        return real_state(self, field, ident)

    def maybe(self, field):
        seen.add(field)
        return real_maybe(self, field)

    T.Step.state, T.Step.maybe = state, maybe
    try:
        runs = [fn() for fn in LEGAL.values()] + [legal_rollback()]
        runs += [m(legal_run()) for m in MUTATIONS.values()]
        for run in runs:
            engine.check(run)
    finally:
        T.Step.state, T.Step.maybe = real_state, real_maybe
    return seen


def test_no_declared_field_goes_unread():
    """A field nobody reads is a field nobody maintains.

    An earlier version of this test asserted only that each field carried a
    non-empty `read_by` in the YAML — which is the schema restating its own
    claim, not evidence. It passed while `approved()` sat in trace.py reading
    nothing.
    """
    unread = (T.STATE_FIELDS | T.PAYLOAD_FIELDS) - _fields_actually_requested()
    assert not unread, (f"trace-schema.yaml declares {sorted(unread)} and no "
                        f"walk asked for it across every run in this suite")


def test_the_schema_does_not_claim_a_reader_that_no_longer_exists():
    named = {i for f in T.SCHEMA["state_fields"] + T.SCHEMA["payload_fields"]
             for i in f["read_by"]}
    assert named <= set(REGISTRY), f"{sorted(named - set(REGISTRY))} reads nothing here"


def test_the_envelope_is_the_catalogs_and_not_this_files():
    """I9 decides `audit(action)` by the envelope, so the envelope had better be
    the one the event catalog requires rather than a list invented beside it."""
    import yaml
    catalog = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1]
                              / "model" / "event-catalog.yaml").read_text(encoding="utf-8"))
    required = {f["field"] for f in catalog["envelope"]["fields"] if f["required"] is True}
    ours = set(T.ENVELOPE) - {"event"}          # the step's key for event_type
    assert ours <= required | {"event_type"}, (
        f"{sorted(ours - required)} is demanded of every event and the catalog "
        f"does not require it")
    # And the direction that actually protects I9. Dropping a field from the
    # schema silently stops I9 checking it — causation_id above all, whose
    # absence lets an out-of-order arrival drive a transition that never
    # legally happened.
    folded = {"event_type", "payload"}          # carried as the step's own shape
    assert required - folded <= ours, (
        f"the catalog requires {sorted(required - folded - ours)} of every "
        f"event and nothing here checks for it")


# ------------------------------------------------------------- the legal runs

@pytest.mark.parametrize("name", sorted(LEGAL))
def test_a_run_the_specification_allows_is_not_refused(name):
    verdict = engine.check(LEGAL[name]())
    assert verdict.ok, (
        f"{name} is legal and was refused by "
        f"{sorted({v['invariant'] for v in verdict.refusal.detail})}: "
        f"{verdict.refusal.summary}")


def test_the_legal_run_is_long_enough_to_be_worth_walking():
    """A one-step trace satisfies almost anything. Thirteen of the fifteen
    negative traces this file used to carry were one step long."""
    assert len(legal_run()) > 20


def test_i12_and_the_rollback_chain_contradict_each_other():
    """Not a fault in the walk, and not one to paper over.

    `transitions.html` §7 sets out the legal rollback and ends it with
    `rev 1 → Published, rev 2 → Superseded`. I12 says a revision only becomes
    superseded because a *successor* was published, and revision 2 has no
    successor — the pointer went back to its parent. Both statements are in the
    approved model and they cannot both hold.

    The walk implements the formula as written, so it refuses the rollback. This
    test records that, and fails the day the model is fixed — which is the point:
    a known contradiction that stops being true should not stay written down.
    """
    verdict = engine.check(legal_rollback())
    assert not verdict.ok
    blame = [v for v in verdict.refusal.detail if v["invariant"] == "I12"]
    assert blame and "revision 2" in blame[0]["why"]
    assert len(verdict.refusal.detail) == 1, (
        "only I12 should object to a legal rollback; the rest is a real bug")


# ------------------------------------------- one field changed, one refusal

def _exam_topics_never_approved_together():
    """I2 asks for a past moment at which every topic was approved *at once*.

    Approving one and withdrawing it before the other lands satisfies
    `∧ₜ O approved(t)` and breaks `O (∧ₜ approved(t))`, which is the operator
    scope the model states and the one this walk implements.
    """
    run = legal_run()
    at = find(run, "NodeApproved", 1)                 # the second topic's approval
    for i in range(at, len(run)):
        run[i] = {**run[i], "approved_nodes": [N2]}   # N1's approval withdrawn
    return run


def _without(run: list[dict], step: int, field: str) -> list[dict]:
    out = [dict(s) for s in run]
    out[step] = {k: v for k, v in out[step].items() if k != field}
    return out


MUTATIONS = {
    # The state that matters is the one the event arrived in — the step before.
    "I1": lambda r: mutate(r, find(r, "NodeGenerated") - 1, course_state="OutlineReview"),
    "I2": lambda r: _exam_topics_never_approved_together(),
    "I3": lambda r: mutate(r, find(r, "PublishRequested"), stale_nodes=[N1]),
    "I4": lambda r: mutate(r, find(r, "(auto)"), event="NodeEdited", node=N1),
    "I5": lambda r: mutate(legal_removal(), 1, committed_outline=[N1, N2]),
    # The verdict at the step that admits the node names a different artifact,
    # so nothing ever screened this one.
    "I6": lambda r: mutate(r, find(r, "GuardrailVerdict", 1), artifact="outline"),
    "I7": lambda r: mutate(r, find(r, "PublishRequested"), current_policy_version="p13"),
    "I8": lambda r: mutate(r, find(r, "NodeGenerated"), used_restricted=[N1]),
    "I9": lambda r: _without(r, find(r, "PublishRequested"), "causation_id"),
    "I10": lambda r: mutate(r, find(r, "LearnersNotified"), event="NodeEdited", node=N1),
    "I11": lambda r: mutate(r, find(r, "LivePointerMoved"),
                            revision_states={1: "Withdrawn"}),
    "I12": lambda r: legal_rollback(),
    "I13": lambda r: mutate(legal_rollback(), 3, re_verified=[]),
    "I14": lambda r: mutate(legal_removal(), 1, course_state="ContentInProgress",
                            node_states={N1: "NodeApproved", N2: "NodeRecovery"},
                            retry_budget_left={N2: False}),
    "I15": lambda r: mutate(r, find(r, "PublishRequested"), current_guardrail_version="g5"),
}


@pytest.mark.parametrize("ident", sorted(MUTATIONS, key=lambda x: int(x[1:])))
def test_each_invariant_catches_a_run_that_breaks_it(ident):
    run = MUTATIONS[ident](legal_run())
    verdict = engine.check(run)
    assert not verdict.ok, f"{ident} accepted a run the specification forbids"
    assert verdict.refusal.kind != "malformed-trace", (
        f"the run for {ident} does not match the schema, so nothing was "
        f"checked: {verdict.refusal.summary}")
    assert any(v["invariant"] == ident for v in verdict.refusal.detail), (
        f"the run was refused, but not by {ident}: "
        f"{sorted({v['invariant'] for v in verdict.refusal.detail})}")


def test_the_refusal_names_the_formula_and_the_step():
    v = engine.check(MUTATIONS["I10"](legal_run()))
    first = v.refusal.detail[0]
    assert first["formula"] and first["event"] and isinstance(first["step"], int)


# ------------------------------------------------------------- fail closed

MISSING = {
    "I3": ("stale_nodes", "PublishRequested"),
    "I7": ("current_policy_version", "PublishRequested"),
    "I14": ("retry_budget_left", "LivePointerMoved"),
    "I2": ("approved_nodes", "OutlineApproved"),
    "I15": ("current_guardrail_version", "PublishRequested"),
}


@pytest.mark.parametrize("ident", sorted(MISSING, key=lambda x: int(x[1:])))
def test_a_missing_fact_refuses_rather_than_permits(ident):
    """Silence is not a pass.

    Every one of these returned `ok` before the trace had a declared shape: a
    published course whose run said nothing about staleness, or about which
    policy was in force, came back clean from the layer whose whole job is to
    notice.
    """
    field, event = MISSING[ident]
    run = legal_run()
    at = find(run, event)
    run[at] = {k: v for k, v in run[at].items() if k != field}
    verdict = engine.check(run)
    assert not verdict.ok, f"{ident} answered ok with {field!r} missing"
    gap = [v for v in verdict.refusal.detail
           if v["invariant"] == ident and v["kind"] == "unrecorded"]
    assert gap, f"{ident} refused, but not as an unrecorded fact: {verdict.refusal.detail}"
    assert field in gap[0]["why"]


def test_an_unfilled_pointer_target_is_named_as_unrecorded():
    """I11 with a live pointer at a revision the run never describes."""
    run = legal_run()
    at = find(run, "LivePointerMoved")
    run[at] = {**run[at], "live_pointer": 9}
    detail = engine.check(run).refusal.detail
    assert any(v["invariant"] == "I11" and v["kind"] == "unrecorded" for v in detail)


# ------------------------------------------------------------ the shape itself

def test_a_field_nobody_declared_is_refused_before_anything_is_checked():
    run = mutate(legal_run(), 5, invented_field=True)
    verdict = engine.check(run)
    assert not verdict.ok and verdict.refusal.kind == "malformed-trace"
    assert "invented_field" in str(verdict.refusal.detail)


def test_a_state_name_the_inventory_does_not_have_is_refused():
    run = mutate(legal_run(), 5, course_state="Drafting")
    verdict = engine.check(run)
    assert not verdict.ok and verdict.refusal.kind == "malformed-trace"


def test_a_run_that_does_not_start_at_the_beginning_is_refused():
    verdict = engine.check(legal_run()[3:])
    assert not verdict.ok and verdict.refusal.kind == "malformed-trace"


def test_a_side_effect_without_an_idempotency_key_is_refused():
    """A retry of a paid call that cannot be told from a first attempt."""
    run = legal_run()
    at = find(run, "NodeGenerated")
    run[at] = {k: v for k, v in run[at].items() if k != "idempotency_key"}
    verdict = engine.check(run)
    assert not verdict.ok
    assert "idempotency_key" in str(verdict.refusal.detail)
