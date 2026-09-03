"""Which guard is answered by which callable — and which are not answered yet.

`guards.yaml` names 38 guards and says who owns each. Twenty are the state
store's or a person's and are not this package's business. Of the rest, some are
implemented here and some are not, and until this file existed the difference
lived in nobody's head and no test. A guard named in the glossary and answered
nowhere is the quietest gap in the system: a reader believes the question is
asked, and nothing anywhere asks it.

Two lists, both checked against the model:

  IMPLEMENTED — the guard and the function that decides it.
  PARTIAL     — owned jointly with a layer this phase does not have. Each says
                which share is missing and where it comes from. These are not
                deferred by choice, and marking them so is the difference
                between a known gap and an unmarked one.
"""
from __future__ import annotations

from .datalog import engine as datalog
from .datalog import structure as datalog_structure
from .opa import engine as opa
from .prolog import engine as prolog
from .schema import engine as schema
from .temporal import engine as temporal
from .z3 import engine as z3

IMPLEMENTED = {
    "schema_valid(artifact)": schema.check,
    "block_schemas_valid(node)": schema.check_blocks,
    "policy_allows(action, role, state)": opa.check,
    "approval_chain_satisfied(revision)": opa.check_approval,
    "feasible(brief)": z3.check,
    "arithmetic_consistent(node)": z3.check_arithmetic,
    "grounded(node)": datalog.check_grounding,
    "no_permission_leak(scope)": datalog.check_permission_leak,
    "skills_grounded(outline)": datalog_structure.check_skills_grounded,
    "references_live(node)": datalog_structure.check_references_live,
    "ordering_acyclic(course)": datalog_structure.check_ordering_acyclic,
    "content_approved(topics(exam))": datalog_structure.check_content_approved,
    "depends_on(node, edited)": datalog_structure.cascade,
    "objectives_covered(scope)": prolog.check_coverage,
    "trace_satisfies_ltl(course)": temporal.check,
}

PARTIAL = {
    "affected(revision)":
        "Datalog can say which nodes a change reaches. Whether a guardrail "
        "version change reaches this revision is the managed service's answer, "
        "and it is not reachable until the guardrail exists.",
    "has_active_readers(revision)":
        "Reader windows live in the state store. Nothing here keeps them, so "
        "the Datalog share has no facts to reason over yet.",
    "guardrail_clean(artifact)":
        "A managed service decides this. There is no local stand-in: writing "
        "one would be a second guardrail with different answers, which is worse "
        "than not having it.",
}
