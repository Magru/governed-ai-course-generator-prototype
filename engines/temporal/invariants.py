"""The fifteen properties, each as the walk that decides it.

The formula text is the specification's and is checked against `invariants.yaml`
by a test — nothing here may claim to check a property the model does not state,
and nothing in the model may go unchecked.

What is *not* done here is parse the formulas. The operators are real and live in
ltl.py; the atoms are domain predicates written out, because `all_nodes_approved`
and `¬∃ stale` are questions about a course, not about strings. A parser would
have to know as much about the domain as these functions do, and would hide it.

Every walk reads the run through `trace.py`, which declares what a run carries.
A walk that needs a fact the run does not carry raises `Unrecorded` and the
engine turns it into a refusal. None of them may answer "ok" from silence.
"""
from __future__ import annotations
from typing import Callable

from .ltl import Violation, eventually, next_step, once, once_now
from .trace import (INITIAL, Step, Trace, admitted, held, missing_envelope,
                    needs_revalidation, removed, unapproved)

Check = Callable[[Trace], list[Violation]]
REGISTRY: dict[str, tuple[str, Check]] = {}


def invariant(ident: str, formula: str):
    def register(fn: Check) -> Check:
        fn.ident = ident                                     # type: ignore[attr-defined]
        fn.formula = formula                                 # type: ignore[attr-defined]
        REGISTRY[ident] = (formula, fn)
        return fn
    return register


def _v(fn, step: Step, why: str, kind: str = "violated") -> Violation:
    return Violation(fn.formula, step.seq, step.event, why, kind)


@invariant("I1", "G(content_generated(N) → course_state = ContentInProgress)")
def i1(trace: Trace) -> list[Violation]:
    """The event fires *into* a state, so the state that matters is the one it
    arrived in — the previous step's. Reading the resulting state instead would
    ask whether the course was still drafting after the node was written, which
    is a different question and one the specification does not pose."""
    bad = []
    for i, s in enumerate(trace):
        if s.event != "NodeGenerated":
            continue
        was = trace.before(i).state("course_state", "I1")
        if was != "ContentInProgress":
            bad.append(_v(i1, s, f"content generated while the revision was {was!r}"))
    return bad


@invariant("I2", "G(exam_generated(E) → O content_approved(topics(E)))")
def i2(trace: Trace) -> list[Violation]:
    """The conjunction sits inside the O: there must be one past moment at which
    every topic was approved together, not a topic here and a topic there.

    Implemented as the model states it. What the model states has a hole, and
    the hole is recorded as an open question in `invariants.yaml` rather than
    quietly patched here: a moment in the past satisfies the formula even if an
    approval has since been withdrawn.
    """
    bad = []
    for i, s in enumerate(trace):
        if s.event != "NodeGenerated" or s.maybe("node_type") != "exam":
            continue
        needed = set(s.state("topics", "I2"))
        if not any(needed <= set(trace[j].state("approved_nodes", "I2"))
                   for j in range(i)):
            bad.append(_v(i2, s, f"exam generated with no past moment at which "
                                 f"{sorted(needed)} were approved together"))
    return bad


@invariant("I3", "G(published(C) → all_nodes_approved(C) ∧ ¬∃ stale(C))")
def i3(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if s.maybe("course_state") != "Published":
            continue
        if open_ := unapproved(s, "I3"):
            bad.append(_v(i3, s, f"published with {sorted(open_)} not approved"))
        if stale := s.state("stale_nodes", "I3"):
            bad.append(_v(i3, s, f"published with {sorted(stale)} stale"))
    return bad


@invariant("I4", "G(node_edited(N) → X needs_revalidation(N))")
def i4(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if s.event != "NodeEdited":
            continue
        node = s.state("node", "I4")
        if not next_step(trace, i, lambda t: node in needs_revalidation(t, "I4")):
            bad.append(_v(i4, s, f"{node} was edited and did not move to "
                                 f"revalidation on the next step"))
    return bad


@invariant("I5", "G(removed(N) → O outline_committed_without(N))")
def i5(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if i == 0:
            continue                     # the initial state is given, not done
        newly = removed(s, "I5") - removed(trace[i - 1], "I5")
        for node in sorted(newly):
            # Inclusive: the commit that drops the node from the outline is the
            # removal. Strict past forbids the only legal way to remove anything.
            if not once_now(trace, i, lambda t, n=node: _committed_without(t, n)):
                bad.append(_v(i5, s, f"{node} was removed with no outline "
                                     f"committed without it"))
    return bad


def _committed_without(step: Step, node: str) -> bool:
    outline = step.maybe("committed_outline")
    return outline is not None and node not in outline


@invariant("I6", "G(generated(A) → O guardrail_checked(A))")
def i6(trace: Trace) -> list[Violation]:
    """`generated(A)` is not the NodeGenerated event.

    The node machine runs ContentDrafting → Generated → OutputGuardrail, so at
    the moment that event fires no verdict can possibly exist yet. What the
    model forbids — "admitting model output that never met the guardrail" — is
    the step *out* of screening, which is where a verdict does exist.
    """
    bad = []
    for i, s in enumerate(trace):
        if i == 0:
            continue                     # see I5 — nothing is "newly" at step 0
        newly = admitted(s, "I6") - admitted(trace[i - 1], "I6")
        for artifact in sorted(newly):
            # Inclusive: the verdict that clears the artifact and the step that
            # admits it are one transition, so strict past finds nothing.
            if not once_now(trace, i, lambda t, a=artifact: _screened(t, a)):
                bad.append(_v(i6, s, f"{artifact} was admitted to the record "
                                     f"without a guardrail verdict"))
    return bad


def _screened(step: Step, artifact: str) -> bool:
    """A verdict was recorded for this artifact — allow or deny alike.

    Read off the GuardrailVerdict events rather than a list kept beside them.
    The events are the record; a parallel list is the same fact written twice.
    """
    return step.event == "GuardrailVerdict" and step.maybe("artifact") == artifact


@invariant("I7", "G(published(C) → policy_version(C) = current ∨ stale(C) ∨ ¬affected(C))")
def i7(trace: Trace) -> list[Violation]:
    return _version_invariant(trace, i7, "policy_version")


@invariant("I15", "G(published(C) → guardrail_version(C) = current ∨ stale(C) ∨ ¬affected(C))")
def i15(trace: Trace) -> list[Violation]:
    return _version_invariant(trace, i15, "guardrail_version")


def _version_invariant(trace: Trace, fn, field: str) -> list[Violation]:
    """Three escapes, and each one must be stated rather than assumed.

    The earlier version defaulted `affected` to True when absent and treated a
    missing `current_*` as "nothing in force", so a published course whose run
    said nothing about versions came back clean. Silence about whether a course
    is running under a superseded policy is exactly the situation this property
    exists to catch.
    """
    ident, bad = fn.ident, []
    for s in trace:
        if s.maybe("course_state") != "Published":
            continue
        stamped = s.state(field, ident)
        current = s.state(f"current_{field}", ident)
        if stamped == current or s.state("stale_nodes", ident):
            continue
        if not s.state("affected", ident):
            continue
        bad.append(_v(fn, s, f"live under {field}={stamped} while {current} is "
                             f"in force, and it is neither stale nor unaffected"))
    return bad


@invariant("I8", "G(restricted_chunk_used(N) → O permission_checked(N))")
def i8(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        if i == 0:
            continue
        prior = set(trace[i - 1].maybe("used_restricted") or [])
        for node in sorted(set(s.maybe("used_restricted") or []) - prior):
            if not once(trace, i, lambda t, n=node:
                        n in (t.maybe("permission_checked") or [])):
                bad.append(_v(i8, s, f"{node} used a restricted source with no "
                                     f"rights check"))
    return bad


@invariant("I9", "G(action → F audit(action))")
def i9(trace: Trace) -> list[Violation]:
    """The audit is the trace.

    `safety.html` §10 answers "no audit" with "one trace per course, every
    action in it", so there is no separate audit store for this walk to look in
    and an `audited` list would be a field nothing writes — decoration wearing a
    checker's name. What makes an action *reconstructable* is the envelope, and
    `event-catalog.yaml` says which fields those are and what breaks without
    each. So `audit(action)` is decided here as: the step carries the envelope.

    Two consequences worth stating rather than hiding. The F collapses: if the
    audit is the trace then the record is written when the action is, and the
    model's only "eventually" has no lag left to permit. And the check is not
    vacuous — the catalog records that no event carries these fields today, so
    this refuses every run that has not been built to the envelope.
    """
    bad = []
    for s in trace:
        if s.event == INITIAL:
            continue
        missing = missing_envelope(s)
        if missing:
            bad.append(_v(i9, s, f"cannot be reconstructed: the record is "
                                 f"missing {missing}", "unrecorded"))
    return bad


@invariant("I10", "G(published(R) → G ¬node_edited(R))")
def i10(trace: Trace) -> list[Violation]:
    bad, published = [], set()
    for s in trace:
        if s.maybe("course_state") == "Published" and s.maybe("revision") is not None:
            published.add(s.fields["revision"])
        if s.event == "NodeEdited" and s.state("revision", "I10") in published:
            bad.append(_v(i10, s, f"revision {s.fields['revision']} was edited "
                                  f"after publication"))
    return bad


@invariant("I11", "G(live(C) = R → published(R))")
def i11(trace: Trace) -> list[Violation]:
    bad = []
    for s in trace:
        live = s.maybe("live_pointer")
        if live is None:
            continue
        states = s.state("revision_states", "I11")
        if live not in states:
            bad.append(_v(i11, s, f"learners are served revision {live} and the "
                                  f"run does not say what state it is in", "unrecorded"))
        elif states[live] != "Published":
            bad.append(_v(i11, s, f"learners are served revision {live}, which "
                                  f"is {states[live]!r}"))
    return bad


@invariant("I12", "G(superseded(R) → O ∃R' (successor(R', R) ∧ published(R')))")
def i12(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        states = s.maybe("revision_states") or {}
        if i == 0:
            continue
        prior = trace[i - 1].maybe("revision_states") or {}
        for rev in sorted(r for r, st in states.items()
                          if st == "Superseded" and prior.get(r) != "Superseded"):
            # Inclusive: the successor takes the pointer on the same transition
            # that costs the parent its own, so strict past sees nothing.
            if not once_now(trace, i, lambda t, r=rev: _successor_published(t, r)):
                bad.append(_v(i12, s, f"revision {rev} was superseded with no "
                                      f"successor published"))
    return bad


def _successor_published(step: Step, rev) -> bool:
    forks = step.maybe("forked_from") or {}
    states = step.maybe("revision_states") or {}
    return any(states.get(child) == "Published"
               for child, parent in forks.items() if parent == rev)


@invariant("I13", "G(rolled_back_to(R) → O re_verified(R))")
def i13(trace: Trace) -> list[Violation]:
    bad = []
    for i, s in enumerate(trace):
        rev = s.maybe("rolled_back_to")
        if rev is None:
            continue
        if not once(trace, i, lambda t, r=rev: r in (t.maybe("re_verified") or [])):
            bad.append(_v(i13, s, f"rolled back to {rev} without re-verifying it"))
    return bad


@invariant("I14", "G(node_held(N) → course_state(rev N) ≠ ContentInProgress)")
def i14(trace: Trace) -> list[Violation]:
    """The revision leaves ContentInProgress on the same transition that spends
    a node's last retry, so the state to read is the resulting one."""
    bad = []
    for s in trace:
        if s.maybe("node_states") is None:
            continue
        stuck = held(s, "I14")
        if stuck and s.state("course_state", "I14") == "ContentInProgress":
            bad.append(_v(i14, s, f"{sorted(stuck)} have no move left while the "
                                  f"revision still reports itself as working"))
    return bad
