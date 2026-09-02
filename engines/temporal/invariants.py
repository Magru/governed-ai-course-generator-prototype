"""The fifteen properties, each as the walk that decides it.

The formula text is the specification's and is checked against `invariants.yaml`
by a test — nothing here may claim to check a property the model does not state,
and nothing in the model may go unchecked.

What is *not* done here is parse the formulas. The operators are real and live in
ltl.py; the atoms are domain predicates written out, because `all_nodes_approved`
and `¬∃ stale` are questions about a course, not about strings. A parser would
have to know as much about the domain as these functions do, and would hide it.
"""
from __future__ import annotations
from typing import Callable

from .ltl import Violation, always, eventually, next_step, once

Trace = list[dict]
Check = Callable[[Trace], list[Violation]]
REGISTRY: dict[str, tuple[str, Check]] = {}


def invariant(ident: str, formula: str):
    def register(fn: Check) -> Check:
        REGISTRY[ident] = (formula, fn)
        return fn
    return register


def _event(step: dict) -> str:
    return step.get("event", "")


def _violation(formula: str, i: int, trace: Trace, why: str) -> Violation:
    return Violation(formula, i, _event(trace[i]), why)


@invariant("I1", "G(content_generated(N) → course_state = ContentInProgress)")
def i1(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if _event(s) == "NodeGenerated" and s.get("course_state") != "ContentInProgress":
            bad.append(_violation(i1.formula, i, trace,
                                  f"content generated while the revision was "
                                  f"{s.get('course_state')!r}"))
    return bad


@invariant("I2", "G(exam_generated(E) → O content_approved(topics(E)))")
def i2(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if _event(s) == "NodeGenerated" and s.get("node_type") == "exam":
            needed = set(s.get("topics") or [])
            approved = {t for j in range(i) for t in (trace[j].get("approved_nodes") or [])}
            missing = needed - approved
            if missing:
                bad.append(_violation(i2.formula, i, trace,
                                      f"exam generated before {sorted(missing)} were approved"))
    return bad


@invariant("I3", "G(published(C) → all_nodes_approved(C) ∧ ¬∃ stale(C))")
def i3(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if s.get("course_state") == "Published":
            if s.get("unapproved_nodes"):
                bad.append(_violation(i3.formula, i, trace,
                                      f"published with {s['unapproved_nodes']} unapproved"))
            if s.get("stale_nodes"):
                bad.append(_violation(i3.formula, i, trace,
                                      f"published with {s['stale_nodes']} stale"))
    return bad


@invariant("I4", "G(node_edited(N) → X needs_revalidation(N))")
def i4(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if _event(s) == "NodeEdited":
            node = s.get("node")
            if not next_step(trace, i, lambda t: node in (t.get("needs_revalidation") or [])):
                bad.append(_violation(i4.formula, i, trace,
                                      f"{node} was edited and did not move to "
                                      f"revalidation on the next step"))
    return bad


@invariant("I5", "G(removed(N) → O outline_committed_without(N))")
def i5(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        for node in s.get("removed_nodes") or []:
            if not once(trace, i, lambda t, n=node: n in (t.get("committed_without") or [])):
                bad.append(_violation(i5.formula, i, trace,
                                      f"{node} was removed with no outline committed without it"))
    return bad


@invariant("I6", "G(generated(A) → O guardrail_checked(A))")
def i6(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if _event(s) in {"NodeGenerated", "OutlineGenerated"}:
            artifact = s.get("node") or s.get("artifact")
            if not once(trace, i, lambda t, a=artifact: a in (t.get("guardrail_checked") or [])):
                bad.append(_violation(i6.formula, i, trace,
                                      f"{artifact} was admitted without a guardrail verdict"))
    return bad


@invariant("I7", "G(published(C) → policy_version(C) = current ∨ stale(C) ∨ ¬affected(C))")
def i7(trace: Trace) -> list[Violation]:
    return _version_invariant(trace, "policy_version", i7.formula)


@invariant("I15", "G(published(C) → guardrail_version(C) = current ∨ stale(C) ∨ ¬affected(C))")
def i15(trace: Trace) -> list[Violation]:
    return _version_invariant(trace, "guardrail_version", i15.formula)


def _version_invariant(trace: Trace, field: str, formula: str) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if s.get("course_state") != "Published":
            continue
        stamped, current = s.get(field), s.get(f"current_{field}")
        if current is None or stamped == current:
            continue
        if s.get("stale") or not s.get("affected", True):
            continue
        bad.append(Violation(formula, i, _event(s),
                             f"live under {field}={stamped} while {current} is in force, "
                             f"and it is neither stale nor unaffected"))
    return bad


@invariant("I8", "G(restricted_chunk_used(N) → O permission_checked(N))")
def i8(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        for node in s.get("used_restricted") or []:
            if not once(trace, i, lambda t, n=node: n in (t.get("permission_checked") or [])):
                bad.append(_violation(i8.formula, i, trace,
                                      f"{node} used a restricted source with no rights check"))
    return bad


@invariant("I9", "G(action → F audit(action))")
def i9(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        action = s.get("action")
        if not action:
            continue
        if eventually(trace, lambda t, a=action: a in (t.get("audited") or []), after=i) is None:
            bad.append(_violation(i9.formula, i, trace,
                                  f"{action} was never audited before the trace ended"))
    return bad


@invariant("I10", "G(published(R) → G ¬node_edited(R))")
def i10(trace: Trace) -> list[Violation]:
    bad, published = [], set()
    for i, s in enumerate(trace):
        if s.get("course_state") == "Published" and s.get("revision") is not None:
            published.add(s["revision"])
        if _event(s) == "NodeEdited" and s.get("revision") in published:
            bad.append(_violation(i10.formula, i, trace,
                                  f"revision {s.get('revision')} was edited after publication"))
    return bad


@invariant("I11", "G(live(C) = R → published(R))")
def i11(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        live = s.get("live_pointer")
        if live is None:
            continue
        states = s.get("revision_states") or {}
        if states.get(live) not in (None, "Published"):
            bad.append(_violation(i11.formula, i, trace,
                                  f"learners are served revision {live}, which is "
                                  f"{states.get(live)!r}"))
    return bad


@invariant("I12", "G(superseded(R) → O ∃R' (successor(R', R) ∧ published(R')))")
def i12(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        for rev in s.get("superseded") or []:
            if not once(trace, i, lambda t, r=rev: (t.get("published_successor_of") or {}).get(str(r))):
                bad.append(_violation(i12.formula, i, trace,
                                      f"revision {rev} was superseded with no successor published"))
    return bad


@invariant("I13", "G(rolled_back_to(R) → O re_verified(R))")
def i13(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        rev = s.get("rolled_back_to")
        if rev is None:
            continue
        if not once(trace, i, lambda t, r=rev: r in (t.get("re_verified") or [])):
            bad.append(_violation(i13.formula, i, trace,
                                  f"rolled back to {rev} without re-verifying it"))
    return bad


@invariant("I14", "G(node_held(N) → course_state(rev N) ≠ ContentInProgress)")
def i14(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if (s.get("held_nodes") or []) and s.get("course_state") == "ContentInProgress":
            bad.append(_violation(i14.formula, i, trace,
                                  f"{s['held_nodes']} have no move left while the "
                                  f"revision still reports itself as working"))
    return bad


for _ident, (_formula, _fn) in REGISTRY.items():
    _fn.formula = _formula        # so each check can name itself in a violation
