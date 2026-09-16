"""Load the transition tables, or refuse to start.

Topology comes from `model/transitions.yaml` and nothing else; the behaviour of
each guard comes from a registry keyed by the glossary's name. Between the two
sits this loader, and its one job is to be certain: every event is one the
catalog declares or one of the reactions listed below, every state is in the
inventory, every guard literal is in the glossary, every non-state endpoint has
a resolver. Anything else stops the machine before it takes a step, and the
message names the row — a machine that starts on a table it half understands
would simply never take the row it did not understand, and nobody would know.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from engines.temporal.trace import EVENTS, NODE_STATES, REVISION_STATES

from . import endpoints
from .guard_expressions import MODEL, Guard, UnknownGuard, glossary, parse

#: Event cells written in parentheses are not events: nothing produces them.
#: They are the revision machine reacting to a change in the node machine, and
#: they are evaluated like (auto) rows after every step.
REACTIONS = {
    "(node → BlockedFinal)": "a node entered BlockedFinal",
    "(node → NodeRecovery)": "a node entered NodeRecovery",
    "(node state changed)": "any node moved",
    "(dependency changed)": "a node this one depends on was edited or removed",
}
AUTO = "(auto)"

#: The qualifier in `Event(q)` is matched against the event's payload.
#: `CheckFailed(layer, nodes)` names the payload's fields rather than a value,
#: so it matches every layer.
_QUALIFIED = re.compile(r"^(\w+)\((.+)\)$")
_ANY = {"any", "layer, nodes"}


class TableRefused(RuntimeError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("the transition table cannot drive a machine:\n  "
                         + "\n  ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Transition:
    machine: str                 # "revision" | "node"
    row: int
    event: str                   # a catalog name, AUTO, or a REACTIONS key
    qualifier: frozenset | None  # payload values this row is restricted to
    sources: frozenset           # state names; empty when source_rule is set
    source_rule: str | None
    guard: Guard
    target: str | None           # a state name; None when target_rule is set
    target_rule: str | None
    note: str | None
    spawn: bool = False

    def label(self) -> str:
        return f"{self.machine}[{self.row}] {self.event}"


def _events(cell: str) -> list[tuple[str, frozenset | None]]:
    if cell == AUTO or cell in REACTIONS:
        return [(cell, None)]
    q = _QUALIFIED.match(cell)
    if q:
        inner = q.group(2).strip()
        if inner in _ANY:
            return [(q.group(1), None)]
        values = [v.strip() for v in re.split(r"[·,]", inner) if v.strip() not in ("…", "")]
        return [(q.group(1), frozenset(values))]
    return [(name.strip(), None) for name in cell.split("·")]


def load(path=None) -> dict[str, list[Transition]]:
    raw = yaml.safe_load((path or MODEL / "transitions.yaml").read_text())
    names = glossary()
    problems: list[str] = []
    table: dict[str, list[Transition]] = {"revision": [], "node": []}
    states = {"revision": REVISION_STATES, "node": NODE_STATES}
    for machine in table:
        for i, row in enumerate(raw[machine]):
            where = f"{machine}[{i}] {row['event']!r}"
            try:
                guard = parse(row["guard"], names, NODE_STATES)
            except UnknownGuard as exc:
                problems.append(f"{where}: {exc}")
                continue
            if guard.complement_of_previous and not _previous_auto(table[machine], row):
                problems.append(f"{where}: 'any of the above fails' has no (auto) row above it")
            source_rule = row.get("from_expression")
            if source_rule and source_rule not in endpoints.SOURCES:
                problems.append(f"{where}: no resolver for source {source_rule!r}")
            target_rule = row.get("to_expression")
            if target_rule and target_rule not in endpoints.TARGETS:
                problems.append(f"{where}: no resolver for target {target_rule!r}")
            if row.get("to_note") and row["to_note"] not in _notes():
                problems.append(f"{where}: no bookkeeping for the note {row['to_note']!r}")
            sources = frozenset(row.get("from") or ())
            targets = row.get("to") or ()
            for s in sources | set(targets if row["to_kind"] != "other_object" else ()):
                if s not in states[machine]:
                    problems.append(f"{where}: {s!r} is not a {machine} state")
            for event, qualifier in _events(row["event"]):
                if event not in EVENTS and event not in REACTIONS:
                    problems.append(f"{where}: {event!r} is not in the event catalog")
                table[machine].append(Transition(
                    machine, i, event, qualifier, sources, source_rule, guard,
                    targets[0] if targets and not target_rule else None,
                    target_rule, row.get("to_note"),
                    spawn=row["to_kind"] == "other_object"))
    if problems:
        raise TableRefused(problems)
    return table


def _notes() -> dict:
    from .bookkeeping import NOTES       # bookkeeping imports the store, not the loader
    return NOTES


def _previous_auto(rows: list[Transition], row: dict) -> Transition | None:
    for t in reversed(rows):
        if t.event == AUTO and t.sources == frozenset(row["from"] or ()):
            return t
    return None


def complement_source(table: dict[str, list[Transition]], t: Transition) -> Transition:
    """The row an 'any of the above fails' row negates."""
    rows = table[t.machine]
    return next(r for r in reversed(rows[: rows.index(t)])
                if r.event == AUTO and r.sources == t.sources
                and not r.guard.complement_of_previous)
