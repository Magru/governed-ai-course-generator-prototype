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

from .actions import PERSON, PRODUCED, REGISTRY, SYSTEM
from .provider.port import GuardrailUnavailable, ProviderUnavailable

#: Events whose side effect the store marks landed when it records them. Any
#: other registered action is done the moment it is issued and recorded.
LANDS = {"OutlineGenerated", "NodeGenerated"}

NEXT = {
    "registered": "ask for a registered action; nothing ran",
    "schema_valid": "resend with exactly the arguments the action declares",
    "policy_allows": "ask someone the policy grants this action to",
    "resource_allowed": "act on a course in your own organisation and audience",
    "legal_in_state": "take the move the course's current state permits",
    "approval_present": "have a person take this action; the system may not",
    "idempotency_key_unused": "nothing to do — it already happened",
    "within_rate_limit": "wait, then retry",
    "effect": "the call is unknown, not failed: recover",
}

#: The OPA action a registered action is judged as, where the policy names it
#: differently. Every other action is judged under its own name.
POLICY_ACTION = {"propose_outline": "generate_outline",
                 "generate_node_content": "generate_node", "generate_image": "generate_node"}

#: The gateway acting on its own behalf — screening, admitting, moving the pointer.
GATEWAY = {"id": "gateway", "kind": SYSTEM}


@dataclass
class Outcome:
    ran: bool
    check: str | None = None
    reason: str = ""
    next_action: str = ""
    key: str | None = None


def key_of(name: str, args: dict, course: str, subject: dict | None = None) -> str:
    """sha256 of the canonical action — the inventory's definition of the key.

    The canonical action includes what it acts on, not only what was asked: an
    approval of a node in revision 2 is not the approval of it in revision 1,
    and an approval after an edit is not the approval before it."""
    canonical = json.dumps({"action": name, "args": args, "course": course,
                            "subject": subject or {}},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class Membrane:
    machine: Any
    course: str
    rate_limit: int = 20
    spent: dict = field(default_factory=dict)
    issued: set = field(default_factory=set)

    def request(self, name: str, args: dict, actor: dict, perform=None) -> Outcome:
        """Run the eight checks, then the effect.

        `perform(key)` is the call itself — a model, a screening — made only
        after every check passed and the key was issued. What it returns joins
        the event's payload. If the provider does not answer, nothing is fired
        and the outcome says so; the caller records the timeout, because the
        table has a row for it and the membrane is not the machine."""
        action = REGISTRY.get(name)
        if action is None:
            return self._no("registered", f"{name!r} is not in the action registry")
        errors = sorted(jsonschema.Draft202012Validator(action.args).iter_errors(args),
                        key=lambda e: list(e.absolute_path))
        if errors:
            return self._no("schema_valid", "; ".join(e.message for e in errors))
        if action.event in PRODUCED and perform is None:
            # Not a refusal a person could meet: a call site that supplies the
            # result itself is a hole in the gateway, and it must not run.
            raise TypeError(f"{name} lands a provider's answer; it needs the call that makes it")
        m = self.machine
        actor = self._authenticated(actor)
        verdict = opa.check(POLICY_ACTION.get(name, name), actor, _brief(m), m.current.state,
                            m.world.policy_data)
        if not verdict.ok:
            return self._no("policy_allows", verdict.refusal.summary)
        if actor.get("course", self.course) != self.course:
            return self._no("resource_allowed", f"{actor.get('id')} does not act on {self.course}")
        if actor.get("kind") == PERSON and actor.get("id") not in m.world.people:
            return self._no("resource_allowed", f"{actor.get('id')} is not in this organisation")
        # A person's act carries who did it — the caller, never a name passed in.
        # A system's does not stand in for a person: the guards that judge an
        # author must go on judging the author.
        payload = dict(args)
        if actor["kind"] == PERSON:
            payload["actor"] = actor["id"]
        rev = m.current
        node = rev.nodes.get(args.get("node")) if args.get("node") else None
        # Content is part of what an approval or an admission acts on. It is not
        # part of what a generation acts on — it is what the generation makes,
        # and the prompt digest in its arguments already names the request.
        acts_on_content = node is not None and action.event not in LANDS
        subject = {"revision": rev.id,
                   "node": json.dumps(node.content, sort_keys=True) if acts_on_content else None}
        key = key_of(name, args, self.course, subject)
        # A repeat is a no-op once the effect has landed. A key issued for a call
        # that never answered has not landed, and retrying it under the same key
        # is exactly what the key is for — the provider deduplicates, we do not
        # pay twice.
        landed = key in m.store.used_keys or (key in self.issued and action.event not in LANDS)
        if landed:
            return Outcome(False, "idempotency_key_unused", "already done",
                           NEXT["idempotency_key_unused"], key)
        if action.event is not None:
            ok, why = self._legal(action.event, {**payload, "idempotency_key": key})
            if not ok:
                return self._no("legal_in_state", why)
        if action.requires in (PERSON, SYSTEM) and actor["kind"] != action.requires:
            return self._no("approval_present",
                            f"{name} needs a {action.requires}; a {actor['kind']} asked")
        if self.spent.get(actor.get("id"), 0) >= self.rate_limit:
            return self._no("within_rate_limit", f"{actor.get('id')} spent {self.rate_limit} actions")
        # Issued before the effect, landed after it — two facts, not one. The
        # store's used_keys means *landed*: it is what NodeRecovery reads to
        # decide whether to regenerate. Recording the key there before the call
        # would make a crash between the two look like a write that landed, and
        # the node would move on with no content.
        self.issued.add(key)
        self.spent[actor.get("id")] = self.spent.get(actor.get("id"), 0) + 1
        if perform is not None:
            try:
                payload.update(perform(key))
            except (ProviderUnavailable, GuardrailUnavailable) as exc:
                return Outcome(False, "effect", str(exc), NEXT["effect"], key)
        produced = PRODUCED.get(action.event)
        if produced and payload.get(produced) is None:
            return Outcome(False, "effect", f"the provider answered without {produced}",
                           NEXT["effect"], key)
        if action.event is not None:
            m.fire(action.event, {**payload, "idempotency_key": key})
        return Outcome(True, key=key)

    def _authenticated(self, actor: dict) -> dict:
        """Who is asking, as the organisation knows them. A role written on the
        request is ignored: a person holds the role the organisation gave them,
        and someone it does not know holds none."""
        if actor.get("kind") == PERSON:
            person = self.machine.world.people.get(actor.get("id")) or {}
            return {"id": actor.get("id"), "kind": PERSON, "role": person.get("role"),
                    **({"course": actor["course"]} if "course" in actor else {})}
        return {"id": actor.get("id"), "kind": actor.get("kind"), "role": actor.get("kind"),
                **({"course": actor["course"]} if "course" in actor else {})}

    def _legal(self, event: str, payload: dict) -> tuple[bool, str]:
        """Is the event legal now, asked before its result exists. A screening's
        verdict is not known until the call is made, so the question is whether
        some verdict has a row here — asking with none would find no row at all."""
        if PRODUCED.get(event) != "verdict":
            return self.machine.permits(event, payload)
        answers = [self.machine.permits(event, {**payload, "verdict": v}) for v in ("allow", "deny")]
        return next((a for a in answers if a[0]), answers[0])

    def _no(self, check: str, reason: str) -> Outcome:
        return Outcome(False, check, reason, NEXT[check])


def _brief(m) -> dict:
    brief = m.current.brief or {}
    return {**brief, "node_count": len(brief.get("nodes") or [])}
