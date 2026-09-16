"""The generation gateway — functional-model.yaml's eleven stages, in order.

   1 schema · 2 policy · 3 guardrail in · 4 routing       the membrane, before any spend
   5 generation                                           the Generator port
   6 guardrail out                                        the Screener port → GuardrailVerdict
   7 block schemas · 8 grounding and rights ·
   9 constraints and coverage · 10 admission              NodeChecks, in the machine
  11 audit                                                the trace

Nothing here decides legality or runs a check the machine runs: the gateway
makes the calls that cost money or leave the tenant, turns their answers into
events, and turns their silence into the Timeout rows the tables already have.
Each stage it passes is written to `stages`, so a run can be shown stage by
stage rather than asserted.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from engines.schema.schemas import OUTLINE

from .membrane import GATEWAY, Membrane
from .provider.port import Prompt
from .retrieval import retrieve
from .screened_text import blocks_of, screened_text

OUTLINE_RULES = ("outline\nPropose modules as topics and exams: titles and learning objectives "
                 "only. Every skill must be one the catalog lists. Return the outline schema.")
NODE_RULES = ("node:{node}\nWrite this node from the sources only. Cite every claim by chunk "
              "id; cite nothing you were not given. Blocks must be catalog block types.")
NODE_SCHEMA = {"type": "object", "required": ["blocks", "cites"],
               "properties": {"blocks": {"type": "array"}, "cites": {"type": "array"}}}


def digest(prompt: Prompt) -> str:
    parts = {"instructions": prompt.instructions, "author": prompt.author,
             "sources": list(prompt.sources)}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


@dataclass
class Pipeline:
    machine: Any
    generator: Any
    screener: Any
    course: str
    kb_chunks: list
    stages: list = field(default_factory=list)
    screenings: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.membrane = Membrane(self.machine, self.course)

    def screen(self, content: str, modality: str, point: str, subject: str):
        """One screening per content, point and guardrail version. The machine
        asks for a verdict inside a guard, and a legality check runs the same
        guard again before the real step; the second asking must get the first
        answer, not a second billed call that may answer differently. A service
        that did not answer is not remembered — it is asked again."""
        memo = (point, subject, _sha(content), self.machine.store.current["guardrail"],
                getattr(self.screener, "version", None))
        if memo not in self.screenings:
            self.screenings[memo] = self.screener.screen(content, modality, point, subject=subject)
        return self.screenings[memo]

    # ── the brief ─────────────────────────────────────────────────────────
    def submit_brief(self, brief: dict, actor: dict) -> None:
        m = self.machine
        m.fire("BriefSubmitted", {"brief": brief, "actor": actor["id"]})
        self._stage(1, "schema · policy", "brief", m.current.state)
        if m.current.state == "BriefValidation":
            self._screen("brief-in", "brief", json.dumps(brief, sort_keys=True), "text")

    # ── the skeleton ──────────────────────────────────────────────────────
    def draft_outline(self, actor: dict) -> None:
        m = self.machine
        prompt = Prompt(self._with_feedback(OUTLINE_RULES, m.current),
                        author=json.dumps({k: m.current.brief[k] for k in ("title", "objectives")}),
                        sources=self._sources())
        self._stage(4, "routing", "outline", type(self.generator).__name__)
        out = self.membrane.request(
            "propose_outline", {"prompt": digest(prompt)}, actor,
            perform=lambda key: {"outline": self._generate(prompt, OUTLINE, "outline")})
        if not out.ran:
            return self._unknown_or_refused(out, {}, "Timeout")
        self._screen("outline-out", "outline", json.dumps(m.current.proposal), "text")

    # ── one node ──────────────────────────────────────────────────────────
    def generate_node(self, node_id: str, actor: dict) -> None:
        m = self.machine
        if m.current.nodes[node_id].state == "Planned":
            m.fire("NodeGenerationRequested", {"node": node_id, "actor": actor["id"]})
        while m.current.nodes[node_id].state == "ContentDrafting":
            node = m.current.nodes[node_id]
            prompt = Prompt(self._with_feedback(NODE_RULES.format(node=node_id), node),
                            author=json.dumps(node.spec, sort_keys=True), sources=self._sources())
            self._stage(4, "routing", node_id, type(self.generator).__name__)
            out = self.membrane.request(
                "generate_node_content", {"node": node_id, "prompt": digest(prompt)}, actor,
                perform=lambda key, p=prompt: {"content": self._generate(p, NODE_SCHEMA, node_id)})
            if not out.ran:
                self._unknown_or_refused(out, {"node": node_id}, "Timeout")
                continue
            if m.current.nodes[node_id].state == "OutputGuardrail":
                self._screen_node(node_id)

    # ── internals ─────────────────────────────────────────────────────────
    def _sources(self) -> tuple:
        audiences = (self.machine.current.brief or {}).get("audience") or []
        self._stage(3, "retrieval · rights filter", "sources", audiences)
        return tuple(f"{c['id']}: {c['text']}" for c in
                     retrieve(self.machine.world, audiences, self.kb_chunks))

    def _with_feedback(self, rules: str, obj) -> str:
        # A repair is a retry that changed the request: the machine-produced
        # reason goes into the instructions, not "try again".
        reason = getattr(obj, "last_refusal", None)
        return rules if not reason else f"{rules}\nThe previous attempt was refused: {reason}"

    def _generate(self, prompt: Prompt, schema: dict, subject: str) -> dict:
        generated = self.generator.generate(prompt, schema)
        self._stage(5, "generation", subject, generated.model_id)
        # Whatever came back lands as it came, and the machine's checks judge
        # it: an empty lesson is refused by the block schema at NodeChecks and
        # repaired with that reason, not mended or discarded here where no
        # trace would show it.
        return generated.content

    def _screen_node(self, node_id: str) -> None:
        content = self.machine.current.nodes[node_id].content or {}
        blocks, text = blocks_of(content), screened_text(content)

        def screen(key):
            verdict = self._verdict("node-out", node_id, text, "text")
            for i, block in enumerate(blocks):
                if verdict.allowed and block.get("type") == "image":
                    verdict = self._verdict("image-out", f"{node_id}.blocks[{i}]",
                                            block.get("src", ""), "image")
            return _as_payload(verdict)

        self._admit(node_id, node_id, _sha(json.dumps(content, sort_keys=True)), screen)

    def _screen(self, point: str, subject: str, content: str, modality: str) -> None:
        self._admit(subject, None, _sha(content),
                    lambda key: _as_payload(self._verdict(point, subject, content, modality)))

    def _verdict(self, point: str, subject: str, content: str, modality: str):
        verdict = self.screen(content, modality, point, subject)
        self._stage(6 if point != "brief-in" else 3, f"guardrail {point}", subject,
                    "allow" if verdict.allowed else f"deny: {verdict.category}")
        return verdict

    def _admit(self, artifact: str, node: str | None, screened: str, screen) -> None:
        """Admission is the screening. The verdict it lands is whatever the
        screener answered inside the call — there is no argument through which
        anyone could state it instead. What was screened is part of the key:
        admitting a repaired outline is a different action from admitting the
        one it replaced."""
        args = {"artifact": artifact, "screened": screened, **({"node": node} if node else {})}
        out = self.membrane.request("admit_to_revision", args, GATEWAY, perform=screen)
        if out.check == "effect":
            self._stage(6, "guardrail", artifact, f"unreachable: {out.reason}")
            self.machine.fire("ServiceUnreachable", {"node": node} if node else {},
                              producer="gateway")
            return
        if out.check == "idempotency_key_unused":
            self._stage(10, "admission", artifact, "already admitted")
            return
        if not out.ran:
            # A screened artifact that cannot be admitted is not a quiet no-op:
            # the node would wait in OutputGuardrail for a verdict nobody sends.
            raise GatewayRefused(f"admission of {artifact}: {out.check}: {out.reason}")
        # Stages 7–9 are NodeChecks, run by the machine on the admitted content.
        target = self.machine.current.nodes.get(node) if node else self.machine.current
        result = target.state
        if target.state in ("ContentDrafting", "OutlineDrafting") and target.last_refusal:
            result = f"{target.state} — repaired: {target.last_refusal}"
        self._stage(10, "checks 7–9 · admission", artifact, result)

    def _unknown_or_refused(self, out, scope: dict, event: str) -> None:
        if out.check in ("effect", "answer"):
            # No answer is a Timeout; an answer in the wrong shape is a ModelError.
            # The table routes both to recovery, and the trace says which it was.
            self._stage(5, "generation", scope.get("node", "outline"), f"{out.check}: {out.reason}")
            self.machine.fire(event if out.check == "effect" else "ModelError", scope,
                              producer="gateway")
            return
        raise GatewayRefused(f"{out.check}: {out.reason} — {out.next_action}")

    def _stage(self, number: int, name: str, subject: str, result) -> None:
        self.stages.append((number, name, subject, result))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _as_payload(verdict) -> dict:
    return {"verdict": "allow" if verdict.allowed else "deny",
            **({"category": verdict.category} if verdict.category else {})}


class GatewayRefused(RuntimeError):
    """The membrane refused the action. Carries the check and the next action."""
