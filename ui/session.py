"""One course on screen: the real machine and gateway behind the buttons.

Nothing here decides anything. Every button is an event the machine judges or
an action the gateway's membrane admits, exactly as in `make run`; a refusal
comes back as the refusal it is. What the page adds is that a person presses
the buttons a person would press, and sees why each step went where it did.

Two modes. **Recorded** answers from the cassette the tests use, so it needs no
network and gives the same answers every time; it has recordings for the
presets below and for nothing else, and says so rather than inventing one.
**Live** asks Gemini and Bedrock Guardrails, through the same ports.
"""
from __future__ import annotations

import copy
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engines import registry  # noqa: E402
from engines.temporal import engine as temporal  # noqa: E402
from gateway.pipeline import GatewayRefused  # noqa: E402
from gateway.provider.recorded import RecordedGenerator, RecordedScreener  # noqa: E402
from machine.refusal import MachineRefused  # noqa: E402
from scenarios import cassette, run, twins, walkthrough as w  # noqa: E402
from scenarios.machine_runs import NOTICE, signatures  # noqa: E402

PRESETS = {
    "course": ("A course that is published", w.BRIEF, "allow"),
    # The fixture's brief, with the size Z3 needs to judge it, so the refusal
    # on screen is the guardrail's and not a question the brief left open.
    "forbidden": ("A forbidden topic", {**twins._twin("01-forbidden-topic.yaml")["brief"], "requested_nodes": 3},
                  "defeating-a-guard"),
    "infeasible": ("A brief that cannot hold", twins._twin("02-contradictory-brief.yaml")["brief"], "allow"),
    "audience": ("An audience not granted", {**w.BRIEF, "id": "mt-course-210", "audience": ["supervisors"]},
                 "allow"),
}


# How many times a person may reject one lesson before the recording runs out.
REVISIONS = 3


def _revised(node: str, round_: int) -> dict:
    """What the recorded model writes after a person rejects a lesson: the same
    lesson, told it was revised, so a Reject on the page is followed by a new
    draft rather than by a recording that has run out."""
    content = copy.deepcopy(w.CONTENT[node])
    first = content["blocks"][0]
    key = "question" if "question" in first else "text"
    first[key] = f"{first[key]} (revised after review {round_})"
    return content


def _recorded(preset: str):
    if preset == "course":
        generator, screener = cassette.course_generator(), cassette.course_screener()
        for node in (w.T1, w.T2, w.T3, w.E1):
            for round_ in range(1, REVISIONS + 1):
                generator.answers[f"node:{node}"].append(_revised(node, round_))
                screener.verdicts.setdefault(("node-out", node), []).append("allow")
        screener.verdicts.setdefault(("image-out", f"{w.T1}.blocks[1]"), []).extend(["allow"] * REVISIONS)
        return generator, screener
    # The refusal presets never reach a model: the brief is refused first.
    return RecordedGenerator({}), RecordedScreener({("brief-in", "brief"): [PRESETS[preset][2]]})


def _live():
    from gateway.provider.bedrock import BedrockScreener
    from gateway.provider.gemini import GeminiGenerator
    return GeminiGenerator(), BedrockScreener()


class Session:
    def __init__(self, mode: str = "recorded", preset: str = "course"):
        self.mode, self.preset = mode, preset
        generator, screener = _live() if mode == "live" else _recorded(preset)
        if mode == "live" and not (screener.guardrail and (screener.version or "").isdigit()):
            raise RuntimeError("live mode needs BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION in .env "
                               "(make guardrail-create writes them)")
        self.p = run.pipeline(generator=generator, screener=screener)
        if mode == "live":
            # The guardrail in force is the one deployed, by its published version.
            self.p.machine.store.current["guardrail"] = screener.version
        self.brief = copy.deepcopy(PRESETS[preset][1])
        self.engine_log: list[dict] = []
        self.messages: list[dict] = []
        self.mark = (0, 0)          # where the stage list and the engine log stood before the last button

    # ── what a person does ──────────────────────────────────────────────
    def submit(self, brief: dict | None = None) -> None:
        self.brief = copy.deepcopy(brief or self.brief)
        self.p.submit_brief(copy.deepcopy(self.brief), run.AUTHOR)
        for _ in range(self.p.machine.store.budget() + 1):
            if self.p.machine.current.state != "OutlineDrafting":
                break
            self.p.draft_outline(run.AUTHOR)

    def approve_outline(self) -> None:
        self.p.machine.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})

    def generate(self, node: str) -> None:
        self.p.generate_node(node, run.AUTHOR)

    def approve(self, node: str) -> None:
        content = self.p.machine.current.nodes[node].content or {}
        images = [f"{node}.blocks[{i}]" for i, b in enumerate(content.get("blocks") or [])
                  if isinstance(b, dict) and b.get("type") == "image"]
        extra = {"visuals_reviewed": images} if images else {}
        out = self.p.membrane.request("approve_node", {"node": node, "what_was_shown": "formal verdict",
                                                       **extra}, run.AUTHOR)
        if not out.ran:
            raise GatewayRefused(f"{out.check}: {out.reason}")

    def reject(self, node: str, reason: str) -> None:
        self.p.machine.fire("NodeRejected", {"node": node, "reason": reason, "actor": run.AUTHOR["id"]})

    def release(self) -> None:
        """A person has looked at what blocked the course and lets it go on."""
        self.p.machine.fire("BlockedInputFixed", {"actor": run.AUTHOR["id"]})

    def course_checks(self) -> None:
        self.p.machine.fire("CourseChecksRequested")

    def sign(self) -> None:
        self.p.machine.fire("ApprovalGranted", {"signatures": signatures(NOTICE)})

    def publish(self) -> None:
        out = self.p.membrane.request("publish_revision", {"revision": self.p.machine.current.id}, run.ADMIN)
        if not out.ran:
            raise GatewayRefused(f"{out.check}: {out.reason}")

    # ── doing it, and saying what happened ──────────────────────────────
    def act(self, name: str, *args) -> dict:
        before = len(self.p.machine.store.steps)
        self.mark = (len(self.p.stages), len(self.engine_log))
        try:
            with _listening(self.engine_log):
                getattr(self, name)(*args)
        except (MachineRefused, GatewayRefused) as exc:
            self.messages.append({"kind": "refused", "text": f"{name}: {exc}"})
            return {"ok": False, "error": str(exc)}
        except Exception as exc:                  # noqa: BLE001 — shown, never swallowed
            self.messages.append({"kind": "error", "text": f"{name}: {type(exc).__name__}: {exc}"})
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        moved = len(self.p.machine.store.steps) - before
        self.messages.append({"kind": "ok", "text": f"{name}: {moved} step(s) recorded"})
        return {"ok": True}

    def snapshot(self) -> dict:
        m = self.p.machine
        rev = m.current
        verdict = temporal.check(m.trace())
        return {
            "mode": self.mode, "preset": self.preset, "brief": self.brief,
            "guardrail": m.store.current["guardrail"],
            "generator": type(self.p.generator).__name__,
            "revision": {"id": rev.id, "state": rev.state, "blocked_at": rev.blocked_at,
                         "last_refusal": rev.last_refusal},
            "revisions": {r.id: r.state for r in m.store.revisions.values()},
            "live_pointer": m.store.live_pointer,
            "nodes": [{"id": n.id, "type": n.spec.get("type"), "skill": n.spec.get("skill"),
                       "topics": n.spec.get("topics"), "state": n.state, "repairs": n.repair_count,
                       "last_refusal": n.last_refusal, "content": n.content}
                      for n in rev.nodes.values()] or _offered(rev),
            "stages": [list(s) for s in self.p.stages][-160:],
            "events": [{"event": s["event"], "state": s.get("course_state")} for s in m.store.steps][-60:],
            "ltl": "every invariant holds" if verdict.ok else verdict.refusal.summary,
            "engine_log": self.engine_log[-40:],
            # What the last button heard, so a stop is told by what caused it
            # and not by a refusal an earlier step already settled.
            "last_act": {"stages": [list(x) for x in self.p.stages[self.mark[0]:]],
                         "engines": self.engine_log[self.mark[1]:]},
            "messages": self.messages[-12:],
        }


def _offered(rev) -> list[dict]:
    """The outline the model offered, before any node exists: a person has to
    see what they are approving, and what was refused if the checks stopped it.
    It is the model's output, so nothing in it is trusted to have a shape."""
    nodes = (rev.proposal or {}).get("nodes") if isinstance(rev.proposal, dict) else None
    state = "Proposed" if rev.state == "OutlineReview" else "Refused"
    return [{"id": str(spec["id"]), "type": spec.get("type"), "skill": spec.get("skill"),
             "topics": spec.get("topics"), "state": state, "repairs": 0, "last_refusal": None, "content": None}
            for spec in (nodes if isinstance(nodes, list) else []) if isinstance(spec, dict) and spec.get("id")]


class _listening:
    """Every refusal an engine gives while a button runs, as the engine gave it.
    The machine keeps only the outcome; the artifact a person acts on — the
    unsat core, the named rule, the leak path — is what the page shows."""

    def __init__(self, log: list):
        self.log, self.saved = log, {}

    def __enter__(self):
        for guard, check in registry.IMPLEMENTED.items():
            self.saved[guard] = check

            def heard(*args, _guard=guard, _check=check, **kwargs):
                verdict = _check(*args, **kwargs)
                refusal = getattr(verdict, "refusal", None)
                if refusal is not None:
                    entry = {"guard": _guard, "engine": refusal.engine, "kind": refusal.kind,
                             "summary": refusal.summary}
                    if not self.log or self.log[-1] != entry:
                        self.log.append(entry)
                return verdict
            registry.IMPLEMENTED[guard] = heard
        return self

    def __exit__(self, *exc):
        registry.IMPLEMENTED.update(self.saved)
        return False
