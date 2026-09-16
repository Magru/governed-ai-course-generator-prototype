"""The machine starts only on a table it fully understands.

Every test here is about the start, not a run: the loader's refusals, and the
agreements between the vocabularies the machine stitches together — the
glossary, the tables, the engine registry, the state inventory and the trace
schema. Each agreement is checked in both directions, because one direction
only proves that what is written down exists, not that what exists is written
down.
"""
from __future__ import annotations

import copy
import pathlib
from itertools import combinations

import pytest
import yaml

from engines.registry import IMPLEMENTED, PARTIAL
from engines.temporal.trace import SCHEMA
from machine import endpoints
from machine.engine_guards import ADAPTERS
from machine.guard_expressions import MODEL, NOT_GUARDS, glossary
from machine.store import DERIVED_TRACE_FIELDS, INVENTORY_TO_TRACE, RevisionRecord, Store
from machine.store_guards import NOT_ASKED_BY_A_ROW, STORE_GUARDS
from machine.transition_table import TableRefused, load

RAW = yaml.safe_load((MODEL / "transitions.yaml").read_text())


def _broken(tmp_path: pathlib.Path, machine: str, row: int, **changes) -> pathlib.Path:
    raw = copy.deepcopy(RAW)
    raw[machine][row].update(changes)
    path = tmp_path / "transitions.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))
    return path


def test_the_vendored_table_loads_with_every_row():
    table = load()
    for machine in ("revision", "node"):
        assert {t.row for t in table[machine]} == set(range(len(RAW[machine])))


@pytest.mark.parametrize("change, says", [
    ({"guard": "schema_valid ∧ looks_fine(brief)"}, "no guard in the glossary is called 'looks_fine'"),
    ({"event": "BriefResubmitted"}, "'BriefResubmitted' is not in the event catalog"),
    ({"to": ["BriefChecked"], "to_raw": "BriefChecked"}, "'BriefChecked' is not a revision state"),
    ({"to_kind": "expression", "to_expression": "wherever it was"}, "no resolver for target 'wherever it was'"),
    ({"to_note": "outline_version +2"}, "no bookkeeping for the note 'outline_version +2'"),
])
def test_a_broken_table_stops_the_machine_and_names_the_row(tmp_path, change, says):
    with pytest.raises(TableRefused) as refused:
        load(_broken(tmp_path, "revision", 1, **change))
    assert any(p.startswith("revision[1]") and says in p for p in refused.value.problems)


def test_every_glossary_guard_is_answered_exactly_once():
    answered = set(STORE_GUARDS) | set(ADAPTERS) | set(NOT_ASKED_BY_A_ROW)
    names = {e["name"] for e in glossary().values()}
    assert answered == names
    assert not (set(STORE_GUARDS) & set(ADAPTERS))


def test_engine_adapters_are_the_registry_and_nothing_beside_it():
    # depends_on answers with a path, so the store asks it at the cascade.
    assert set(ADAPTERS) | {"depends_on(node, edited)"} == set(IMPLEMENTED)
    assert set(PARTIAL) <= set(STORE_GUARDS)


def test_the_phrases_that_are_not_guards_are_exactly_the_ones_the_table_uses():
    used = {phrase for m in ("revision", "node") for t in load()[m]
            for phrase in t.guard.evidence_only}
    assert used == set(NOT_GUARDS)


def test_every_unresolved_endpoint_in_the_model_has_a_resolver_and_no_more():
    listed = {e["raw"] for e in RAW["open_questions"]["unresolved_endpoints"]}
    assert listed == set(endpoints.SOURCES) | set(endpoints.TARGETS)


def test_the_store_speaks_the_trace_schema_field_for_field():
    store = Store({"thresholds": {"repair_budget": 2}},
                  {"policy": "p", "guardrail": "g", "catalog": "c", "kb": "k"})
    rev = store.new_revision()
    assert isinstance(rev, RevisionRecord)
    declared = {f["name"] for f in SCHEMA["state_fields"]}
    assert set(store.snapshot(rev)) == declared
    mapped = {f for v in INVENTORY_TO_TRACE.values() if isinstance(v, list) for f in v}
    assert mapped | DERIVED_TRACE_FIELDS == declared


def test_every_inventory_variable_reaches_the_trace_or_says_why_not():
    inventory = yaml.safe_load((MODEL / "state-inventory.yaml").read_text())["variables"]
    assert {v["variable"] for v in inventory} == set(INVENTORY_TO_TRACE)


def _exclusive(a, b) -> bool:
    if a.guard.complement_of_previous or b.guard.complement_of_previous:
        return True
    for x in a.guard.literals:
        for y in b.guard.literals:
            if x.name != y.name:
                continue
            if x.op is None and y.op is None and x.negated != y.negated:
                return True
            if x.op == y.op == "=" and x.value != y.value:
                return True
            if {x.op, y.op} == {"=", "∉"}:
                eq, nin = (x, y) if x.op == "=" else (y, x)
                if eq.value in nin.value:
                    return True
    return False


def _ambiguous(table) -> list[str]:
    """Rows that could both hold from one state and go different places. The
    machine takes the first, so an ambiguity would never raise — it would just
    quietly make table order a rule nobody wrote."""
    out = []
    for machine, rows in table.items():
        for a, b in combinations(rows, 2):
            if a.event != b.event or a.row == b.row:
                continue
            if a.qualifier and b.qualifier and not a.qualifier & b.qualifier:
                continue
            if not (a.sources & b.sources or a.source_rule or b.source_rule):
                continue
            if (a.target, a.target_rule) == (b.target, b.target_rule):
                continue
            if not _exclusive(a, b):
                out.append(f"{a.label()} / {b.label()}")
    return out


def test_no_two_rows_from_one_state_can_both_hold():
    assert _ambiguous(load()) == []


def test_the_ambiguity_check_can_fail(tmp_path):
    # Drop the literal that separates two OutlineRepair rows.
    path = _broken(tmp_path, "revision", 21, guard="¬has_outline(revision)")
    assert any("revision[20]" in pair for pair in _ambiguous(load(path)))
