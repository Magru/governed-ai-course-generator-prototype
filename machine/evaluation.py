"""Deciding a row's guard: three values, not two.

A guard is true, false, or undecidable — a fact it needs is not there. The
third value is never folded into the other two. A negated undecidable literal
is still undecidable, and so is the complement of an undecidable row, which
matters in StaleReview: if the guardrail cannot be asked, "any of the above
fails" must not withdraw a live course on the strength of a question nobody
answered.

Engine verdicts are cached for the length of one trace step. The machine asks
the same question several times while it looks for the row that holds — the
pass row, then each CheckFailed row — and a formal engine run as a subprocess
is not free. The cache is keyed on the step count, so nothing survives a move.
"""
from __future__ import annotations

from engines.contract import Verdict

from .engine_guards import ADAPTERS, Context
from .guard_expressions import NODE_IN_STATE
from .store_guards import STORE_GUARDS, ServiceDown, Undecidable
from .transition_table import AUTO, complement_source

#: The states whose pass row is a batch of formal checks, and whose failure is
#: therefore reported as a CheckFailed event carrying the engine's artifact.
CHECK_STATES = {("revision", "OutlineChecks"), ("revision", "WholeCourseChecks"),
                ("node", "NodeChecks")}


class Evaluator:
    def __init__(self, machine) -> None:
        self.m = machine
        self._cache: dict = {}
        self._at = -1

    def forget(self) -> None:
        self._cache.clear()

    # ── rows ──────────────────────────────────────────────────────────────
    def holds(self, t, rev, node, payload) -> tuple[bool, str]:
        value, reason = self.decide(t, rev, node, payload)
        return value is True, reason

    def decide(self, t, rev, node, payload) -> tuple[bool | None, str]:
        g = t.guard
        if g.complement_of_previous:
            value, reason = self.decide(complement_source(self.m.table, t), rev, node, payload)
            return (None if value is None else not value), f"complement of: {reason}"
        if g.exists_node:
            undecided = []
            for candidate in rev.nodes.values():
                value, reason = self._conjunction(g, rev, candidate, payload)
                if value:
                    return True, f"{candidate.id}: {reason}"
                if value is None:
                    undecided.append(reason)
            return (None, "; ".join(undecided)) if undecided else (False, "no node matches")
        return self._conjunction(g, rev, node, payload)

    def _conjunction(self, g, rev, node, payload) -> tuple[bool | None, str]:
        ctx = Context(self.m, rev, node, payload)
        for lit in g.literals:
            try:
                value, why = self._literal(lit, ctx)
            except ServiceDown:
                raise                    # the table has a row for this; not an unknown to swallow
            except Undecidable as exc:
                return None, str(exc)
            if value == lit.negated:
                return False, f"{lit.raw} does not hold" + (f": {why}" if why else "")
        return True, "holds"

    # ── literals ──────────────────────────────────────────────────────────
    def _literal(self, lit, ctx) -> tuple[bool, str]:
        if lit.name == NODE_IN_STATE:
            return ctx.node.state == lit.value, ""
        if lit.name in STORE_GUARDS:
            return bool(STORE_GUARDS[lit.name](lit, ctx)), ""
        verdict = self.verdict(lit, ctx)
        return verdict.ok, "" if verdict.ok else str(verdict.refusal)

    def verdict(self, lit, ctx) -> Verdict:
        steps = len(self.m.store.steps)
        if steps != self._at:
            self._cache.clear()
            self._at = steps
        key = (lit.name, lit.arg, ctx.rev.id, ctx.node.id if ctx.node else None)
        if key not in self._cache:
            verdict = ADAPTERS[lit.name](lit, ctx)
            self._cache[key] = verdict
            self._note_rights(lit, ctx, verdict)
        return self._cache[key]

    def _note_rights(self, lit, ctx, verdict: Verdict) -> None:
        """permission_checked and used_restricted are what the leak check found,
        written down where the trace can carry them — not a second leak check."""
        if lit.name != "no_permission_leak(scope)":
            return
        checked = [ctx.node.id] if ctx.node else [n for n in ctx.rev.nodes]
        ctx.rev.permission_checked.update(checked)
        if not verdict.ok:
            ctx.rev.used_restricted.update(p["node"] for p in verdict.refusal.detail)

    # ── checks that fail become events ────────────────────────────────────
    def check_failure(self, machine: str, obj) -> dict | None:
        if (machine, obj.state) not in CHECK_STATES:
            return None
        rev = obj if machine == "revision" else self.m.rev_of(obj)
        node = obj if machine == "node" else None
        rows = [t for t in self.m.table[machine] if obj.state in t.sources
                and (t.event == AUTO or t.event == "CheckFailed")]
        # The failure rows' own engine literals are asked first — OPA's refusal
        # is terminal and is only on the CheckFailed(opa) row at NodeChecks,
        # so reading the pass row alone would never reach it.
        ordered = [t for t in rows if t.event == "CheckFailed"] + [t for t in rows if t.event == AUTO]
        literals, seen = [], set()
        for t in ordered:
            for lit in t.guard.literals:
                if lit.name in ADAPTERS and (lit.name, lit.arg) not in seen:
                    seen.add((lit.name, lit.arg))
                    literals.append(lit)
        ctx = Context(self.m, rev, node, {})
        for lit in literals:
            if lit.name in ADAPTERS:
                verdict = self.verdict(lit, ctx)
                if not verdict.ok:
                    r = verdict.refusal
                    failure = {"layer": r.engine, "reason": r.summary, "refusal": r}
                    if node is not None:
                        failure["node"] = node.id
                    elif isinstance(r.detail, list):
                        failure["nodes"] = sorted({d["node"] for d in r.detail
                                                   if isinstance(d, dict) and "node" in d})
                    return failure
        return None
