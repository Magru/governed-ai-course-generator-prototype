#!/usr/bin/env python3
"""docs/test-matrix.md, generated from a run of the tests rather than written.

Each row is a test function: the check, the layer that owns it, what it expects
(the test's name is written as that sentence), and what happened on this run.
A parametrised test is one row with its count. The tests the specification says
must exist are mapped to the ones that discharge them, and a promise nothing
here keeps is listed as a gap rather than left out.

    python tools_test_matrix.py           run the tests, rewrite the file
    python tools_test_matrix.py --check   run them, and fail if the file is stale

Exit 1 if any test failed, or if --check finds the file out of date.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
from collections import Counter, defaultdict

import pytest

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "docs" / "test-matrix.md"

# The owner column of safety.html's failure-mode table, plus the parts of this
# repository that keep its own guarantees.
LAYER = {
    "test_engine_z3": "Z3", "test_engine_opa": "OPA", "test_engine_prolog": "Prolog",
    "test_engine_datalog": "Datalog", "test_datalog_structure": "Datalog",
    "test_engine_schema": "JSON Schema", "test_engine_temporal": "Temporal logic",
    "test_ltl_combinators": "Temporal logic", "test_engine_contract": "Every engine",
    "test_machine_table": "State machine", "test_machine_runs": "State machine",
    "test_machine_conformance": "State machine", "test_machine_after_publication": "State machine",
    "test_one_line_of_work": "State machine", "test_exam_waits_for_its_topics": "State machine",
    "test_draft_follows_the_rules_in_force": "State machine",
    "test_cascade_simulation": "State machine",
    "test_gateway_membrane": "Gateway", "test_gateway_forgery": "Gateway",
    "test_gateway_idempotency": "Gateway", "test_gemini_schema": "Gateway", "test_gateway_answers_it_can_vouch_for": "Gateway",
    "test_lesson_depth": "Gateway",
    "test_gateway_screened_text": "Guardrail", "test_bedrock_screener": "Guardrail",
    "test_live_guardrail": "Guardrail", "test_prompt_positions": "Prompt architecture",
    "test_injection_surfaces": "Prompt architecture",
    "test_end_to_end": "End to end", "test_walkthrough": "End to end", "test_ui_session": "End to end",
    "test_twins_match_the_specification": "Specification", "test_guard_coverage": "Specification",
    "test_isolation": "Repository", "test_leak_scan": "Repository",
}
ORDER = ["State machine", "OPA", "Z3", "Datalog", "Prolog", "Temporal logic", "JSON Schema",
         "Every engine", "Gateway", "Guardrail", "Prompt architecture", "End to end",
         "Specification", "Repository"]

# safety.html §5, "The tests that must exist". A row names the tests here that
# discharge the promise, or says why nothing does.
PROMISED = [
    ("test_author_param_widening_refused", "refused at gate, model not called",
     ["test_injection_surfaces::test_an_audience_beyond_the_authors_grant_is_refused_before_any_model_is_called",
      "test_engine_opa::test_an_audience_they_were_not_granted_is_refused_by_name"], ""),
    ("test_author_text_cannot_skip_a_check", "generation proceeds, every layer still runs",
     ["test_injection_surfaces::test_an_authors_sentence_asking_to_skip_the_checks_switches_none_of_them_off"], ""),
    ("test_source_instruction_is_inert", "content generated normally",
     ["test_injection_surfaces::test_an_instruction_in_a_source_reaches_the_model_only_as_a_source_and_generation_goes_on"],
     ""),
    ("test_source_instruction_is_recorded", "admission screen fires, trace entry", [],
     "gap: none of the five screening points reads a retrieved source, so the attempt "
     "is inert but not recorded (fixtures/evil-twins/07)"),
    ("test_catalog_metadata_is_not_prompt", "external catalog import refused",
     ["test_engine_schema::test_a_block_carries_only_what_its_catalog_row_defines"],
     "partial: the catalog is a reviewed, versioned fixture and block schemas are closed; "
     "there is no import path, so no refusal of one to test"),
    ("test_output_cannot_request_an_action", "model output naming an action does not cause one",
     ["test_injection_surfaces::test_a_model_answer_that_names_an_action_causes_none_and_its_extra_field_is_refused",
      "test_gateway_membrane::test_an_action_the_registry_gives_a_person_is_refused_to_the_system"], ""),
    ("test_pii_redacted_before_admission", "redaction precedes context entry", [],
     "gap: the invented organisation's sources carry no personal data, and no redaction step exists"),
    ("test_secret_never_enters_prompt", "credential never assembled in",
     ["test_injection_surfaces::test_no_credential_reaches_what_the_live_adapter_sends_or_what_is_screened"],
     "the Gemini adapter, holding a key, against a stand-in for its API"),
]


RANK = {"passed": 0, "xpassed": 1, "xfailed": 1, "skipped": 1, "failed": 2, "error": 2}


class Collector:
    def __init__(self):
        self.items, self.outcomes, self.live = {}, {}, []

    def pytest_collection_finish(self, session):
        # After deselection: a test `-m` left out is not a row of this run.
        for item in session.items:
            path, line, _ = item.location
            self.items[item.nodeid] = (pathlib.Path(path).stem, item.originalname, path, line + 1)

    def pytest_deselected(self, items):
        self.live += [(pathlib.Path(i.location[0]).stem, i.originalname) for i in items]

    def pytest_runtest_logreport(self, report):
        # The worst of setup, call and teardown: a teardown that errors after a
        # passing call is not a pass.
        if report.failed:
            outcome = "failed" if report.when == "call" else "error"
        elif report.skipped:
            outcome = "xfailed" if hasattr(report, "wasxfail") else "skipped"
        elif report.when == "call":
            outcome = "xpassed" if hasattr(report, "wasxfail") else "passed"
        else:
            return
        held = self.outcomes.get(report.nodeid)
        if held is None or RANK[outcome] > RANK[held]:
            self.outcomes[report.nodeid] = outcome


def _intro(path: pathlib.Path) -> str:
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    return " ".join(doc.split("\n\n")[0].split())


def _sentence(name: str) -> str:
    return name.removeprefix("test_").replace("_", " ")


def render(c: Collector) -> str:
    functions = defaultdict(Counter)
    where = {}
    for nodeid, (module, name, path, line) in c.items.items():
        functions[(module, name)][c.outcomes.get(nodeid, "not run")] += 1
        where.setdefault((module, name), (path, line))
    unmapped = sorted({m for m, _ in functions} - LAYER.keys())
    if unmapped:
        raise SystemExit(f"no layer for {unmapped}: add them to LAYER")

    def fact(key) -> str:
        counts = functions[key]
        total = sum(counts.values())
        if counts["passed"] == total:
            return "passed" if total == 1 else f"passed ×{total}"
        return ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))

    def ref(key) -> str:
        path, line = where[key]
        return f"[`{key[1]}`](../{path}#L{line})"

    totals = Counter(o for counts in functions.values() for o, n in counts.items() for _ in range(n))
    tag = json.loads((ROOT / "model.lock").read_text())["tag"]
    lines = ["# Test matrix", "",
             f"Generated by `make test-matrix` from a run of `pytest -m \"not live\"` against the "
             f"specification at `{tag}`. Do not edit by hand: CI regenerates it and fails if it differs.", "",
             f"**{len(c.items)} tests** in {len(functions)} test functions: "
             + ", ".join(f"{n} {k}" for k, n in sorted(totals.items()))
             + "." + (f" {len(c.live)} more need the real provider and run only under `make live`."
                      if c.live else ""), "",
             "Each test's name is the sentence it checks; the column *expects* is that name read aloud.", "",
             "## The tests the specification says must exist", "",
             "`safety.html` §5 lists eight. Each is discharged by the tests named here, or marked as a gap.", "",
             "| promised | expects | discharged by | result |", "|---|---|---|---|"]
    for promised, expects, by, note in PROMISED:
        keys = [tuple(b.split("::")) for b in by]
        missing = [k for k in keys if k not in functions]
        if missing:
            raise SystemExit(f"{promised} names tests that do not exist: {missing}")
        result = "; ".join(sorted({fact(k) for k in keys})) if keys else "—"
        cell = "<br>".join([ref(k) for k in keys] + ([f"*{note}*"] if note else []))
        lines.append(f"| `{promised}` | {expects} | {cell} | {result} |")
    for layer in ORDER:
        modules = [m for m in LAYER if LAYER[m] == layer and any(k[0] == m for k in functions)]
        if not modules:
            continue
        lines += ["", f"## {layer}", ""]
        for module in modules:
            lines += [f"**`{module}.py`** — {_intro(ROOT / 'tests' / f'{module}.py')}", "",
                      "| check | expects | result |", "|---|---|---|"]
            for key in sorted((k for k in functions if k[0] == module), key=lambda k: where[k][1]):
                lines.append(f"| {ref(key)} | {_sentence(key[1])} | {fact(key)} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    c = Collector()
    code = pytest.main(["tests", "-q", "-m", "not live", "-p", "no:cacheprovider"], plugins=[c])
    text = render(c)
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run make test-matrix and commit it")
            return 1
        print(f"{OUT.relative_to(ROOT)} is current")
    else:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
