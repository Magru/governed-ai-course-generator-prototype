"""Temporal operators over a finite trace.

No model checker. The specification's invariants are evaluated by walking a
trace that has already happened, which is a smaller problem than checking a
model and a different one: it asks whether *this* run was legal, not whether
some run could be.

Finiteness is the subtlety. On an infinite trace `F φ` means "eventually"; on a
finite one it can only mean "before the trace ends", and a run cut short by a
crash satisfies nothing. That is stated where it matters rather than hidden: an
`F` that fails at the end of a trace is reported as unfulfilled, not as false.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Sequence

Step = dict
Predicate = Callable[[Step], bool]


@dataclass(frozen=True)
class Violation:
    formula: str
    step: int
    event: str
    why: str
    kind: str = "violated"
    # "violated"   — the run did something the property forbids.
    # "unfulfilled" — an F that never came true before the trace ended. On a
    #                 finite trace that is not the same as false, and saying so
    #                 is the difference between "this run is illegal" and "this
    #                 run is not finished".
    # "unrecorded"  — the run does not carry what it would take to decide. It
    #                 refuses like the others, because absence of a verdict is
    #                 never a permissive verdict, but it names a gap in the
    #                 recorder rather than a fault in the run.

    def __str__(self) -> str:
        return f"step {self.step} ({self.event}): {self.why}"


def always(trace: Sequence[Step], phi: Predicate) -> int | None:
    """G φ — the first step where φ fails, or None."""
    for i, step in enumerate(trace):
        if not phi(step):
            return i
    return None


def eventually(trace: Sequence[Step], phi: Predicate, *, after: int = 0) -> int | None:
    """F φ — the first step at or after `after` where φ holds, or None.

    None here means unfulfilled rather than false: on a finite trace there is no
    later step to look at, and the difference matters for anything that promises
    an action is eventually audited."""
    for i in range(after, len(trace)):
        if phi(trace[i]):
            return i
    return None


def next_step(trace: Sequence[Step], i: int, phi: Predicate) -> bool:
    """X φ — φ at i+1. False at the end of a trace: there is no next step."""
    return i + 1 < len(trace) and phi(trace[i + 1])


def once(trace: Sequence[Step], i: int, phi: Predicate) -> bool:
    """O φ — φ at some step strictly before i. The only past-tense operator the
    specification uses, and the one most of its invariants are built from."""
    return any(phi(trace[j]) for j in range(i))


def once_now(trace: Sequence[Step], i: int, phi: Predicate) -> bool:
    """O φ, inclusive of the present step.

    The specification's past-tense obligations are mostly discharged by the same
    transition that creates them: the outline commit that drops a node *is* the
    removal, and the guardrail verdict that admits content *is* the admission.
    Read strictly, those obligations can never have been met, and a check built
    on the strict operator refuses every legal run — which four of them did.

    Where the evidence must genuinely predate the event, `once` is still the
    right operator and is still used.
    """
    return any(phi(trace[j]) for j in range(i + 1))


def until(trace: Sequence[Step], phi: Predicate, psi: Predicate) -> bool:
    """φ U ψ — φ holds from the start until ψ does, and ψ does."""
    for step in trace:
        if psi(step):
            return True
        if not phi(step):
            return False
    return False
