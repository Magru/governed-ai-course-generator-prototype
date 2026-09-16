"""The membrane every action passes — safety.html §3, eight checks, cheapest first.

  1 registered(name)            unknown action → refuse, nothing runs
  2 schema_valid(args)          wrong shape, or an extra field → refuse
  3 policy_allows(actor, action) OPA
  4 resource_allowed(actor, course)
  5 idempotency_key_unused(op)  a repeat is a no-op, not a second effect
  6 legal_in_state(action)      the transition table decides — the machine is asked
  7 approval_present(action)    wherever the registry's Requires column names a person
  8 within_rate_limit(actor)

Idempotency comes before legality (spec-v2.8): a repeat of something that
already happened has moved the course on, and asked in the other order it is
refused as illegal and the person is told to take a move they already took.

Each refusal names its check and a safe next action, because a refusal with no
next action is a dead end for the person who met it. When all eight pass, the
key is issued *before* the effect — the order that makes a repeat a no-op
rather than a second effect — and the store marks it landed only once the
effect is recorded.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import jsonschema

from engines.opa import engine as opa

from .actions import PERSON, REGISTRY

NEXT = {
    "registered": "ask for a registered action; nothing ran",
    "schema_valid": "resend with exactly the arguments the action declares",
    "policy_allows": "ask someone the policy grants this action to",
    "resource_allowed": "act on a course in your own organisation and audience",
    "legal_in_state": "take the move the course's current state permits",
    "approval_present": "have a person take this action; the system may not",
    "idempotency_key_unused": "nothing to do — it already happened",
    "within_rate_limit": "wait, then retry",
}

#: The OPA action each registered action is judged as. The policy knows three.
POLICY_ACTION = {"propose_outline": "generate_outline",
                 "generate_node_content": "generate_node", "generate_image": "generate_node"}


@dataclass
class Outcome:
    ran: bool
    check: str | None = None
    reason: str = ""
    next_action: str = ""
    key: str | None = None


def key_of(name: str, args: dict, course: str) -> str:
    """sha256 of the canonical action — the inventory's definition of the key."""
    canonical = json.dumps({"action": name, "args": args, "course": course},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class Membrane:
    machine: Any
    course: str
    rate_limit: int = 20
    spent: dict = field(default_factory=dict)
    issued: set = field(default_factory=set)

    def request(self, name: str, args: dict, actor: dict) -> Outcome:
        action = REGISTRY.get(name)
        if action is None:
            return self._no("registered", f"{name!r} is not in the action registry")
        errors = sorted(jsonschema.Draft202012Validator(action.args).iter_errors(args),
                        key=lambda e: list(e.absolute_path))
        if errors:
            return self._no("schema_valid", "; ".join(e.message for e in errors))
        m = self.machine
        if name in POLICY_ACTION:
            verdict = opa.check(POLICY_ACTION[name], actor, _brief(m), m.current.state,
                                m.world.policy_data)
            if not verdict.ok:
                return self._no("policy_allows", verdict.refusal.summary)
        if actor.get("course", self.course) != self.course:
            return self._no("resource_allowed", f"{actor.get('id')} does not act on {self.course}")
        if actor.get("kind") == PERSON and actor.get("id") not in m.world.people:
            return self._no("resource_allowed", f"{actor.get('id')} is not in this organisation")
        payload = {**args, "actor": actor.get("id")} if "actor" not in args else dict(args)
        key = key_of(name, args, self.course)
        if key in self.issued:
            return Outcome(False, "idempotency_key_unused", "already issued",
                           NEXT["idempotency_key_unused"], key)
        if action.event is not None:
            ok, why = m.permits(action.event, {**payload, "idempotency_key": key})
            if not ok:
                return self._no("legal_in_state", why)
        if action.requires == PERSON and actor.get("kind") != PERSON:
            return self._no("approval_present", f"{name} needs a person; {actor.get('kind')} asked")
        if self.spent.get(actor.get("id"), 0) >= self.rate_limit:
            return self._no("within_rate_limit", f"{actor.get('id')} spent {self.rate_limit} actions")
        # Issued before the effect, landed after it — two facts, not one. The
        # store's used_keys means *landed*: it is what NodeRecovery reads to
        # decide whether to regenerate. Recording the key there before the call
        # would make a crash between the two look like a write that landed, and
        # the node would move on with no content.
        self.issued.add(key)
        self.spent[actor.get("id")] = self.spent.get(actor.get("id"), 0) + 1
        if action.event is not None:
            m.fire(action.event, {**payload, "idempotency_key": key})
        return Outcome(True, key=key)

    def _no(self, check: str, reason: str) -> Outcome:
        return Outcome(False, check, reason, NEXT[check])


def _brief(m) -> dict:
    brief = m.current.brief or {}
    return {**brief, "node_count": len(brief.get("nodes") or [])}
