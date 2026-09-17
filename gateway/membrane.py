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

import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import jsonschema

from engines.opa import engine as opa
from machine.refusal import MachineRefused

from .action_subject import key_of, subject_of
from .actions import PERSON, PRODUCED, REGISTRY, SYSTEM
from .provider.port import GuardrailUnavailable, ProviderUnavailable


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
    "answer": "the provider answered in a shape that was not asked for: recover",
}

#: The OPA action a registered action is judged as, where the policy names it
#: differently. Every other action is judged under its own name.
POLICY_ACTION = {"propose_outline": "generate_outline",
                 "generate_node_content": "generate_node", "generate_image": "generate_node"}

#: The gateway acting on its own behalf — screening, admitting, moving the pointer.
GATEWAY = MappingProxyType({"id": "gateway", "kind": SYSTEM})   # read-only: its id is who acted


@dataclass
class Outcome:
    ran: bool
    check: str | None = None
    reason: str = ""
    next_action: str = ""
    key: str | None = None


@dataclass
class Membrane:
    machine: Any
    course: str
    rate_limit: int = 20
    window_s: float = 60.0
    spent: dict = field(default_factory=dict)    # actor → times of the actions in the window
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
        if (action.event in PRODUCED) != (perform is not None):
            # Not a refusal a person could meet: a call site that supplies the
            # result itself is a hole in the gateway, and it must not run.
            # Only an action that lands a provider's answer makes a call, and it
            # always does. A call attached to any other action could hand back
            # fields — an actor, a node — that the checks above never saw.
            raise TypeError(f"{name}: a provider call belongs to exactly the actions that land its answer")
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
        key = key_of(name, args, self.course, subject_of(m, args, action.event))
        # A repeat is a no-op once the effect has landed, and what has landed is
        # the store's to remember, not this object's: a gateway restarted after
        # notifying learners must still know it did. A key issued for a call that
        # never answered has not landed, and retrying it under the same key is
        # exactly what the key is for — the provider deduplicates, we do not pay
        # twice. A read lands nothing and is remembered only here.
        landed = key in m.store.used_keys or (key in self.issued and action.event is None)
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
        now = time.monotonic()
        # A ceiling per window, not per lifetime. Admission is not under it: the
        # gateway screens what the machine sends it to screen, a rule change can
        # send a whole draft at once, and what bounds that is the retry budget,
        # not a count that would leave half a draft unscreened.
        recent = [t for t in self.spent.get(actor.get("id"), []) if now - t < self.window_s]
        self.spent[actor.get("id")] = recent
        if name != "admit_to_revision" and len(recent) >= self.rate_limit:
            return self._no("within_rate_limit",
                            f"{actor.get('id')} spent {self.rate_limit} actions in {self.window_s:.0f} s")
        # Issued before the effect, landed after it — two facts, not one. The
        # store's used_keys means *landed*: it is what NodeRecovery reads to
        # decide whether to regenerate. Recording the key there before the call
        # would make a crash between the two look like a write that landed, and
        # the node would move on with no content.
        self.issued.add(key)
        self.spent[actor.get("id")].append(now)
        if perform is not None:
            try:
                answer, wrong = _answer(action.event, perform(key))
            except (ProviderUnavailable, GuardrailUnavailable) as exc:
                return Outcome(False, "effect", str(exc), NEXT["effect"], key)
            if wrong:
                return Outcome(False, "answer", wrong, NEXT["answer"], key)
            payload.update(answer)
        if action.event is not None:
            try:
                m.fire(action.event, {**payload, "idempotency_key": key})
            except MachineRefused as exc:
                if perform is None:
                    raise
                # The course moved while the provider was answering — an exam
                # whose topic was edited mid-call is sent back to wait. The
                # answer was paid for and does not land; the key stays unused.
                return Outcome(False, "legal_in_state", str(exc), NEXT["legal_in_state"], key)
            # Recorded only once the step is: a refusal inside the machine rolls
            # the store back and leaves the key unused, so the act can be retried.
            m.store.used_keys.add(key)
        return Outcome(True, key=key)

    def _authenticated(self, actor: dict) -> dict:
        """Who is asking, as the organisation knows them. A role written on the
        request is ignored: a person holds the role the organisation gave them,
        and someone it does not know holds none. The system is the gateway
        object itself, not any request that calls itself a system.

        The membrane is an in-process boundary: the service in front of it
        authenticates a person's session and passes the id it proved. Proving
        that id is outside this prototype; using nothing else is not."""
        course = {"course": actor["course"]} if "course" in actor else {}
        if actor is GATEWAY:
            return {"id": GATEWAY["id"], "kind": SYSTEM, "role": SYSTEM, **course}
        if actor.get("kind") == PERSON:
            person = self.machine.world.people.get(actor.get("id")) or {}
            return {"id": actor.get("id"), "kind": PERSON, "role": person.get("role"), **course}
        return {"id": actor.get("id"), "kind": "unauthenticated", "role": None, **course}

    def _legal(self, event: str, payload: dict) -> tuple[bool, str]:
        """Is the event legal now, asked before its result exists. A screening's
        verdict is not known until the call is made, so the question is whether
        some verdict has a row here — asking with none would find no row at all."""
        produced = PRODUCED.get(event)
        in_force = self.machine.store.current["guardrail"]
        if produced == "notice_screening":
            # Only a clean screening lets a notice go; if even that has no row
            # here, nothing is worth screening.
            return self.machine.permits(event, {**payload, produced: {
                "verdict": "allow", "guardrail_version": in_force}})
        if produced != "verdict":
            return self.machine.permits(event, payload)
        answers = [self.machine.permits(event, {**payload, "verdict": v}) for v in ("allow", "deny")]
        return next((a for a in answers if a[0]), answers[0])

    def _no(self, check: str, reason: str) -> Outcome:
        return Outcome(False, check, reason, NEXT[check])


def _answer(event: str, result) -> tuple[dict, str | None]:
    """The one field a provider's answer may set, checked for its shape. Anything
    else the call returned is dropped, so it cannot stand in for an argument the
    checks judged."""
    produced = PRODUCED[event]
    value = (result or {}).get(produced) if isinstance(result, dict) else None
    if produced == "notice_screening":
        screening, wrong = _answer("GuardrailVerdict", value)
        return ({} if wrong else {produced: screening}), wrong
    if produced == "verdict":
        category = result.get("category") if isinstance(result, dict) else None
        version = result.get("guardrail_version") if isinstance(result, dict) else None
        if value not in ("allow", "deny") or not (category is None or isinstance(category, str)):
            return {}, "the screening answered with no verdict"
        if not isinstance(version, str) or not version:
            # A verdict is stamped with the version that gave it; one that
            # cannot say which version it came from cannot be stamped honestly.
            return {}, "the screening answered without the guardrail version that gave it"
        return {"verdict": value, "guardrail_version": version,
                **({"category": category} if category else {})}, None
    if not isinstance(value, dict):
        # A structured-output call that returns no object did not answer the
        # question it was asked; the table's row for an unknown answer takes it.
        return {}, f"the provider answered without {produced} as an object"
    return {produced: value}, None


def _brief(m) -> dict:
    brief = m.current.brief or {}
    return {**brief, "node_count": len(brief.get("nodes") or [])}
