"""The shape of a run, as `model/trace-schema.yaml` declares it.

Nothing here decides a property. This module answers the question that has to be
settled before any property can be decided: what does the trace carry, and what
does it mean when it carries nothing.

Two rules run through it.

Absence is not permission. A check whose antecedent fires and whose consequent
field is missing does not get to say "ok" — it says the run did not record what
it would take to decide. That is a refusal with an artifact, which is what the
architecture promises, rather than a silent pass, which is what the earlier
version did for a published course with no staleness field.

Facts about a node are read off `node_states` and nowhere else. Approved,
admitted, held, removed and needs-revalidation are all the same fact seen from
different sides, and storing them separately is how two copies of one fact
drift apart.
"""
from __future__ import annotations
import pathlib
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

import yaml

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "model" / "trace-schema.yaml"
INVENTORY_PATH = SCHEMA_PATH.parent / "state-inventory.yaml"
INITIAL = "(initial)"
AUTO = "(auto)"    # a guard firing; the tables' own name for it


class Unrecorded(Exception):
    """The run does not carry the fact this check would need to decide.

    Raised inside a check and turned into a refusal at the engine boundary —
    never allowed to escape as an exception, because an exception is not an
    artifact a person can act on.
    """

    def __init__(self, ident: str, step: int, field: str) -> None:
        super().__init__(f"{ident} cannot be decided at step {step}: "
                         f"the run does not record {field!r}")
        self.ident, self.step, self.field = ident, step, field


def _load(path: pathlib.Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:                                  # noqa: BLE001
        raise RuntimeError(f"the model is not vendored: {exc}") from exc


SCHEMA = _load(SCHEMA_PATH)
STATE_FIELDS = {f["name"] for f in SCHEMA["state_fields"]}
PAYLOAD_FIELDS = {f["name"] for f in SCHEMA["payload_fields"]}
ENVELOPE = list(SCHEMA["envelope"]["required_on_every_event"])
SIDE_EFFECTING = set(SCHEMA["side_effecting"]["events"])

_catalog = _load(SCHEMA_PATH.parent / "event-catalog.yaml")
EVENTS = {INITIAL, AUTO}
for _group in ("commands", "events"):
    for _e in _catalog[_group]:
        for _n in ([_e["name"]] if "name" in _e else _e["names"]):
            EVENTS.add(_n.split("(")[0].strip())

_inventory = {v["variable"]: v for v in _load(INVENTORY_PATH)["variables"]}
REVISION_STATES = set(_inventory["revision.state"]["valid_values"])
NODE_STATES = set(_inventory["node.state"]["valid_values"])

# Past the output guardrail: the node's content is in the record. This is what
# "generated(A)" means in I6 — not the NodeGenerated event, which the node
# machine places *before* screening.
ADMITTED = {"NodeChecks", "NodeRepair", "Validated", "NodeApproved",
            "NeedsRevalidation", "BlockedFinal"}


@dataclass(frozen=True)
class Step:
    seq: int
    event: str
    fields: Mapping[str, Any]

    def state(self, field: str, ident: str) -> Any:
        """A state fact the check cannot do without."""
        if field not in self.fields:
            raise Unrecorded(ident, self.seq, field)
        return self.fields[field]

    def maybe(self, field: str) -> Any:
        """A fact whose absence is not itself a failure — an empty list of
        removed nodes and an unrecorded one are the same thing only where the
        check is looking for the presence of trouble, never its absence."""
        return self.fields.get(field)

    def nodes(self, ident: str) -> dict[str, str]:
        return dict(self.state("node_states", ident))


class Trace(Sequence[Step]):
    def __init__(self, steps: list[Step]) -> None:
        self._steps = steps

    def __len__(self) -> int:
        return len(self._steps)

    def __getitem__(self, i):                                # type: ignore[override]
        return self._steps[i]

    def __iter__(self) -> Iterator[Step]:
        return iter(self._steps)

    def before(self, i: int) -> Step:
        """The state the event at step i arrived in — the previous step.

        The whole reason a step carries one state rather than two. Step 0 is the
        initial state and carries no event, so no check ever asks for its before.
        """
        if i == 0:
            raise Unrecorded("(schema)", 0, "a step before the initial state")
        return self._steps[i - 1]


# ------------------------------------------------------------------ building

def build(raw: list[dict]) -> tuple[Trace, list[str]]:
    """Turn authored dicts into a trace, reporting everything wrong with it.

    Problems are returned rather than raised so the engine can refuse with all
    of them at once. A trace that fails here is never checked: deciding
    properties about a run whose shape is wrong produces confident nonsense.
    """
    problems: list[str] = []
    if not raw:
        return Trace([]), ["the run is empty — there is nothing to decide"]

    steps = []
    for i, row in enumerate(raw):
        event = row.get("event")
        if event is None:
            problems.append(f"step {i}: no event; step 0 must carry {INITIAL!r}")
            event = INITIAL
        if i == 0 and event != INITIAL:
            problems.append(f"step 0 carries {event!r}; the first step is the "
                            f"initial state and must carry {INITIAL!r}")
        if i > 0 and event == INITIAL:
            problems.append(f"step {i}: {INITIAL!r} appears again; a run has one start")

        fields = {k: v for k, v in row.items() if k != "event"}
        unknown = sorted(set(fields) - STATE_FIELDS - PAYLOAD_FIELDS - set(ENVELOPE)
                         - {"idempotency_key"})
        if unknown:
            problems.append(f"step {i} ({event}): carries {unknown}, which "
                            f"trace-schema.yaml does not declare")

        if event not in EVENTS:
            problems.append(f"step {i}: {event!r} is not in event-catalog.yaml. "
                            f"A transition the tables mark automatic carries "
                            f"{AUTO!r}; a guard firing is not an event.")
        problems += _state_name_problems(i, event, fields)
        steps.append(Step(i, event, fields))

    return Trace(steps), problems


def missing_envelope(step: "Step") -> list[str]:
    """The envelope fields this step does not carry.

    `event-catalog.yaml` lists them with, for each, the thing that breaks
    without it — a reused id silently deleting a real event, a missing causation
    letting an out-of-order arrival drive a transition that never legally
    happened. Whether they are present is I9's question, not this module's:
    `build` decides whether the run has the declared shape, and a shape check
    that also graded the record would be a second owner for one question.
    """
    if step.event == INITIAL:
        return []
    missing = [f for f in ENVELOPE if f != "event" and f not in step.fields]
    if step.event in SIDE_EFFECTING and "idempotency_key" not in step.fields:
        missing.append("idempotency_key")
    return missing


def _state_name_problems(i: int, event: str, fields: Mapping) -> list[str]:
    out = []
    course = fields.get("course_state")
    if course is not None and course not in REVISION_STATES:
        out.append(f"step {i} ({event}): course_state {course!r} is not a "
                   f"revision state in state-inventory.yaml")
    for node, state in (fields.get("node_states") or {}).items():
        if state not in NODE_STATES:
            out.append(f"step {i} ({event}): node {node} is in {state!r}, "
                       f"which is not a node state")
    for rev, state in (fields.get("revision_states") or {}).items():
        if state not in REVISION_STATES:
            out.append(f"step {i} ({event}): revision {rev} is in {state!r}, "
                       f"which is not a revision state")
    return out


# ------------------------------------------------------- derived predicates

def unapproved(step: Step, ident: str) -> set[str]:
    return {n for n, s in step.nodes(ident).items()
            if s not in ("NodeApproved", "Removed")}


def admitted(step: Step, ident: str) -> set[str]:
    return {n for n, s in step.nodes(ident).items() if s in ADMITTED}


def removed(step: Step, ident: str) -> set[str]:
    return {n for n, s in step.nodes(ident).items() if s == "Removed"}


def needs_revalidation(step: Step, ident: str) -> set[str]:
    return {n for n, s in step.nodes(ident).items() if s == "NeedsRevalidation"}


def held(step: Step, ident: str) -> set[str]:
    """In recovery with nothing left to spend — invariants.yaml's own definition."""
    budget = step.state("retry_budget_left", ident)
    return {n for n, s in step.nodes(ident).items()
            if s == "NodeRecovery" and not budget.get(n, False)}
