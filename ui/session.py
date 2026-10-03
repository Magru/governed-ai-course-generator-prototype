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

# What an author fills in. The walkthrough's brief also lists a skeleton of
# nodes; an author does not draw the outline — the model proposes it — so the
# page asks for the count instead, which is what Z3 judges. Z3 never guesses a
# count the brief leaves out, so the field is the author's to fill.
_COURSE = {**{k: v for k, v in w.BRIEF.items() if k != "nodes"}, "requested_nodes": len(w.BRIEF["nodes"])}
FIELDS = ("title", "audience", "objectives", "minutes_per_lesson", "requested_nodes")

PRESETS = {
    "course": ("A course that is published", _COURSE, "allow"),
    # The fixture's brief, with the size Z3 needs to judge it, so the refusal
    # on screen is the guardrail's and not a question the brief left open.
    "forbidden": ("A forbidden topic", {**twins._twin("01-forbidden-topic.yaml")["brief"], "requested_nodes": 3},
                  "defeating-a-guard"),
    "infeasible": ("A brief that cannot hold", twins._twin("02-contradictory-brief.yaml")["brief"], "allow"),
    "audience": ("An audience not granted", {**_COURSE, "id": "mt-course-210", "audience": ["supervisors"]},
                 "allow"),
}


def form_options() -> dict:
    """What the form offers: the organisation's audiences and the catalog's
    skills, by their labels, and the limits the organisation sets — shown so a
    person knows them, and checked by Z3 whatever the page lets them type."""
    world = run.pipeline().machine.world
    return {"audiences": [{"id": a["slug"], "label": a["label"]} for a in world.org["organisation"]["audiences"]],
            "skills": [{"id": k["id"], "label": k["label"]} for k in world.catalog["skills"]],
            "limits": {"minutes_per_lesson": world.thresholds["max_minutes_per_lesson"],
                       "requested_nodes": world.thresholds["max_nodes_per_course"],
                       "audience": world.thresholds["max_audience_breadth"]}}


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
        # A person may reject the outline too; the recorded model answers with
        # the same outline, which is what a recording can honestly do.
        generator.answers["outline"].extend(copy.deepcopy(w.OUTLINE) for _ in range(REVISIONS))
        screener.verdicts[("outline-out", "outline")].extend(["allow"] * REVISIONS)
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
    def submit(self, fields: dict | None = None) -> None:
        """The brief is what the person filled in, under the example's id. In
        Recorded mode the title stays the example's: the recorded guardrail
        answered for that text and no other, so passing a new one would be a
        verdict nobody gave. Everything else is judged by the real engines."""
        example = PRESETS[self.preset][1]
        if fields is not None and not isinstance(fields, dict):
            raise GatewayRefused("the brief must be an object of fields")
        if fields:
            if self.mode == "recorded" and fields.get("title", example["title"]) != example["title"]:
                raise GatewayRefused("in Recorded mode the title is the example's — the recorded guardrail "
                                     "answered for that text only. Switch to Live to write your own.")
            picked = {k: fields[k] for k in FIELDS if fields.get(k) not in (None, "")}
            self.brief = {"id": example["id"], **picked}
        self.p.submit_brief(copy.deepcopy(self.brief), run.AUTHOR)
        self._draft()

    def _draft(self) -> None:
        for _ in range(self.p.machine.store.budget() + 1):
            if self.p.machine.current.state != "OutlineDrafting":
                break
            self.p.draft_outline(run.AUTHOR)

    def reject_outline(self, reason: str) -> None:
        """The person sends the outline back; the model is asked again and
        told exactly this reason, as it is told a check's."""
        if not isinstance(reason, str) or not reason.strip():
            raise GatewayRefused("a rejection needs a reason: it is what the next draft is told")
        self.p.machine.fire("OutlineRejected", {"reason": reason.strip(), "actor": run.AUTHOR["id"]})
        self._draft()

    def remove_node(self, node: str) -> None:
        """The person edits the outline: the node goes, and so does every
        exam's claim to test it — an exam that names a node the outline does
        not have is what the trace refuses at the end. The edited outline goes
        through the outline's checks again, never straight to approval."""
        nodes = copy.deepcopy((self.p.machine.current.proposal or {}).get("nodes") or [])
        if not isinstance(node, str) or node not in {n.get("id") for n in nodes}:
            raise GatewayRefused(f"{node!r} is not in the outline")
        kept = [n for n in nodes if n.get("id") != node]
        for n in kept:
            if isinstance(n.get("topics"), list):
                n["topics"] = [t for t in n["topics"] if t != node]
        # Two edits the outline's checks would let through and the course could
        # not survive: an empty outline sends the machine back to drafting with
        # nobody to draft, and an exam over nothing breaks the trace at the end.
        if any(n.get("type") == "exam" and not n.get("topics") for n in kept):
            raise GatewayRefused("the exam would test nothing; remove the exam first, or keep one of its topics")
        if not any(n.get("type") != "exam" for n in kept):
            raise GatewayRefused("an outline needs at least one topic; reject it instead to have it drafted again")
        self.p.machine.fire("OutlineRevised", {"outline": {"nodes": kept}, "actor": run.AUTHOR["id"]})

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
