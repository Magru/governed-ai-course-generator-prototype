"""Getting facts into pyDatalog, and the two things it will not forgive.

Both were found by running it, not by reading about it, and both are the kind of
thing that turns a formal layer into a layer that appears to work.

**A negated relation must have at least one clause.** `~visible(C, A)` over a
relation with no facts does not mean "nothing is visible" — it raises
`Predicate without definition`. An audience that can see nothing is exactly the
case a leak check exists for, so every negated relation is seeded with a row no
real datum can equal.

**Transitive closure must be written left-recursive.** These two rules are
logically identical:

    reaches(A, B) <= prerequisite(A, X) & reaches(X, B)     # right — hangs
    reaches(A, B) <= reaches(A, X) & prerequisite(X, B)     # left  — terminates

On an acyclic graph both answer. On a graph with a cycle the right-recursive
form never returns, and a cycle is precisely what `ordering_acyclic` is looking
for — the check would hang on the only input it was written to catch.
"""
from __future__ import annotations

from ..contract import EngineUnavailable

ENGINE = "datalog"

#: No identifier in any fixture can equal this, so a seeded row can never join.
NOTHING = "\x00 no such id"


def pydatalog():
    try:
        from pyDatalog import pyDatalog
    except ImportError as exc:                    # noqa: BLE001
        raise EngineUnavailable(f"pyDatalog is not installed: {exc}") from exc
    return pyDatalog


def session(terms: str, seed: dict[str, int]):
    """A cleared engine with its terms declared and its negated relations seeded.

    Rules are *not* loaded here. pyDatalog resolves a rule against the relations
    that exist when the rule is read, so loading before the facts leaves the
    rule's own head undefined and the query raises. Facts first, then `rules`.
    """
    pd = pydatalog()
    pd.clear()
    pd.create_terms(terms)
    for relation, arity in seed.items():
        pd.assert_fact(relation, *[NOTHING] * arity)
    return pd


def rules(pd, text: str):
    """Load the rules once the base is complete. See `session`."""
    pd.load(text)
    return pd


def answers(pd, query: str) -> list[tuple]:
    """Rows for a query, with the seeded rows removed.

    The seed exists so a negated relation resolves; it is scaffolding and never
    data. It has to be filtered rather than merely ignored, because a seeded row
    in a *recursive* relation joins with itself: seeding `prerequisite` produced
    `reaches(NOTHING, NOTHING)` and the cycle check reported a cycle in a course
    that had none.
    """
    found = pd.ask(query)
    rows = sorted(found.answers) if found else []
    return [row for row in rows if NOTHING not in row]
