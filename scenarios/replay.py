"""Play a scenario through the machine and say where it diverged.

A scenario is a list of beats. Each beat is one event with its payload and what
the specification says should be true after it — the revision's state, some
node states, a counter. The harness fires the event, compares, and keeps
going: a run that stops at the first mismatch hides the second, and the second
is often the one that explains the first. At the end the whole trace goes to
the temporal engine, because a run can be in the right state at every beat and
still have got there illegally.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engines.contract import Verdict
from engines.temporal import engine as temporal
from machine.machine import Machine, MachineRefused


@dataclass(frozen=True)
class Beat:
    label: str                       # the specification's own step number or name
    event: str
    payload: dict = field(default_factory=dict)
    course: str | None = None        # the current revision's state afterwards
    nodes: dict = field(default_factory=dict)
    check: tuple = ()                # (description, callable(machine) -> bool)
    refused: str | None = None       # a stop the specification requires, by its reason


@dataclass
class Result:
    mismatches: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    ltl: Verdict | None = None

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.refused

    def report(self) -> str:
        lines = [f"✗ {m}" for m in self.mismatches] + [f"⊘ {r}" for r in self.refused]
        if self.ltl is not None:
            lines.append("LTL: every invariant holds" if self.ltl.ok
                         else f"LTL: {self.ltl.refusal.summary}")
        return "\n".join(lines) or "every beat as specified"


def play(m: Machine, beats: list[Beat]) -> Result:
    result = Result()
    for beat in beats:
        try:
            m.fire(beat.event, beat.payload)
        except MachineRefused as exc:
            if beat.refused is None or beat.refused not in str(exc):
                result.refused.append(f"{beat.label} {beat.event}: {exc}")
            continue
        if beat.refused is not None:
            result.mismatches.append(f"{beat.label}: {beat.event} was permitted, and the "
                                     f"specification stops it ({beat.refused})")
            continue
        rev = m.current
        if beat.course and rev.state != beat.course:
            result.mismatches.append(f"{beat.label}: course is {rev.state}, expected {beat.course}")
        for node, expected in beat.nodes.items():
            actual = rev.nodes[node].state if node in rev.nodes else None
            if actual != expected:
                result.mismatches.append(f"{beat.label}: {node} is {actual}, expected {expected}")
        for description, holds in beat.check:
            if not holds(m):
                result.mismatches.append(f"{beat.label}: {description}")
    result.ltl = temporal.check(m.trace())
    return result
