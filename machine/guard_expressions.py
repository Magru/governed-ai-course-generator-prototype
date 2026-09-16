"""The guard column, read as expressions rather than as strings.

The transition tables do not contain guard names. They contain what a person
writes on a whiteboard: `schema_valid ∧ ¬policy_allows(author, audience)`, a
name abbreviated where the row above already gave its argument, a comparison
(`blocked_at = brief`), a quantifier (`∃ node: BlockedFinal`), and sometimes a
sentence after a dash. Matching those strings exactly would make the machine
fall over the first time the prose is tidied; ignoring what does not parse
would make it start on a table it does not understand.

So this module does neither. It parses every guard into literals, maps each
literal to one of the glossary's 38 names by its bare name, and refuses — with
the row — anything it cannot place. The two phrases that are not guards at all
are listed below with the reason each is not one, so a third cannot slip in.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

import yaml

MODEL = pathlib.Path(__file__).resolve().parents[1] / "model"

#: Phrases in the guard column that are not guards. Each is resolved elsewhere,
#: and the reason says where. A test holds this table to exactly the leftovers.
NOT_GUARDS = {
    "constraint violated":
        "the CheckFailed event is the evidence; a guard here would re-run the "
        "check the event already reports",
    "any of the above fails":
        "the complement of the (auto) row above it in the same state; the "
        "loader resolves it to that row's guard, negated",
}

#: A qualifier written after a guard rather than inside its argument list.
QUALIFIERS = {"under current versions": "current_versions"}


class UnknownGuard(ValueError):
    """A literal the glossary does not name. The machine must not start."""


@dataclass(frozen=True)
class Literal:
    name: str                     # the glossary's canonical name, or a form below
    negated: bool = False
    arg: str | None = None        # as written; None when the row abbreviated it
    op: str | None = None         # "=" or "∉" for a comparison
    value: str | tuple[str, ...] | None = None
    qualifier: str | None = None
    raw: str = ""

#: Not a glossary name: a bare state inside ∃, meaning "that node is in it".
NODE_IN_STATE = "node.state"


@dataclass(frozen=True)
class Guard:
    literals: tuple[Literal, ...] = ()
    exists_node: bool = False     # ∃ node: the conjunction holds for some node
    complement_of_previous: bool = False
    evidence_only: tuple[str, ...] = ()   # NOT_GUARDS phrases this guard leans on
    raw: str = ""
    names: frozenset = field(default_factory=frozenset)


def glossary() -> dict[str, dict]:
    """Bare name → the glossary entry. Two entries with one bare name would make
    every abbreviated literal ambiguous, so that is refused here."""
    entries = yaml.safe_load((MODEL / "guards.yaml").read_text())["guards"]
    index: dict[str, dict] = {}
    for entry in entries:
        bare = entry["name"].split("(")[0]
        if bare in index:
            raise UnknownGuard(f"two glossary entries share the bare name {bare!r}")
        index[bare] = entry
    return index


def _split_top(text: str, sep: str = "∧") -> list[str]:
    """Split on ∧ outside parentheses — `guardrail_clean(text ∧ images)` is one
    literal, not two."""
    parts, depth, current = [], 0, []
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == sep and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


_COMPARE = re.compile(r"^(\w+)(\([^)]*\))?\s*(=|∉)\s*(.+)$")
_ATOM = re.compile(r"^(\w+)(\((.*)\))?$")
_STATE = re.compile(r"^[A-Z][A-Za-z]+$")


def _literal(term: str, names: dict[str, dict], node_states: set[str]) -> Literal:
    raw, negated = term, term.startswith("¬")
    term = term.lstrip("¬").strip()
    qualifier = None
    for phrase, tag in QUALIFIERS.items():
        if term.endswith(" " + phrase):
            term, qualifier = term[: -len(phrase)].strip(), tag
    if _STATE.match(term):
        if term not in node_states:
            raise UnknownGuard(f"{raw!r}: {term} is not a node state")
        return Literal(NODE_IN_STATE, negated, op="=", value=term, raw=raw)
    compare = _COMPARE.match(term)
    atom = None if compare else _ATOM.match(term)
    bare = (compare or atom).group(1) if (compare or atom) else None
    if bare not in names:
        raise UnknownGuard(f"{raw!r}: no guard in the glossary is called {bare!r}")
    canonical = names[bare]["name"]
    if compare:
        value = compare.group(4).strip()
        if compare.group(3) == "∉":
            value = tuple(v.strip() for v in value.strip("{}").split(","))
        arg = compare.group(2)[1:-1] if compare.group(2) else None
        return Literal(canonical, negated, arg, compare.group(3), value, qualifier, raw)
    return Literal(canonical, negated, atom.group(3), qualifier=qualifier, raw=raw)


def parse(text: str, names: dict[str, dict], node_states: set[str]) -> Guard:
    raw = text
    text = text.split(" — ")[0].strip()
    if text in ("", "—"):
        return Guard(raw=raw)
    if text in NOT_GUARDS and text == "any of the above fails":
        return Guard(complement_of_previous=True, evidence_only=(text,), raw=raw)
    exists = text.startswith("∃ node:")
    if exists:
        text = text[len("∃ node:"):].strip()
    literals, evidence = [], []
    for term in _split_top(text):
        if term in NOT_GUARDS:
            evidence.append(term)
            continue
        literals.append(_literal(term, names, node_states))
    return Guard(tuple(literals), exists, False, tuple(evidence), raw,
                 frozenset(l.name for l in literals))
