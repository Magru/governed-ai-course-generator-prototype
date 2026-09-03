"""The five refusals, each run against the engine that owns it.

Before any machine exists. The point is to show that every layer refuses on its
own and hands back something to act on — the assembly comes later, and if a
refusal only works inside the pipeline it is the pipeline being tested, not the
layer.
"""
from __future__ import annotations
import pathlib, sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engines.contract import EngineUnavailable, Verdict      # noqa: E402
from engines.datalog import engine as datalog                # noqa: E402
from engines.opa import engine as opa                        # noqa: E402
from engines.prolog import engine as prolog                  # noqa: E402
from engines.temporal import engine as temporal              # noqa: E402
from scenarios.legal_run import N1, find, legal_run, mutate  # noqa: E402
from engines.z3 import engine as z3engine                    # noqa: E402

F = ROOT / "fixtures"


def _load(name: str) -> dict:
    return yaml.safe_load((F / name).read_text(encoding="utf-8"))


ORG = _load("organisation.yaml")
KB = _load("kb.yaml")
VISIBILITY = {k: v for k, v in KB["resolved_visibility"].items() if k != "source"}
POLICY_DATA = {"grants": {p["id"]: {"may_author_for": p["may_author_for"]}
                          for p in ORG["people"]},
               "thresholds": ORG["thresholds"]}


def unsatisfiable_brief() -> Verdict:
    twin = _load("evil-twins/02-contradictory-brief.yaml")
    return z3engine.check(twin["brief"], ORG["thresholds"])


def audience_not_granted() -> Verdict:
    return opa.check("submit_brief",
                     {"id": "author-1", "role": "course-author"},
                     {"audience": ["supervisors"], "node_count": 3, "minutes_per_lesson": 20},
                     "AwaitingBrief", POLICY_DATA)


def restricted_source() -> Verdict:
    twin = _load("evil-twins/03-restricted-source.yaml")
    return datalog.check_permission_leak(twin["brief"]["nodes"], KB["articles"],
                                         twin["brief"]["audience"], VISIBILITY)


def objective_not_covered() -> Verdict:
    return prolog.check_coverage(
        "mt-course-001", ["bench-safety", "tool-inspection"],
        [{"id": "mt-node-001", "skill": "bench-safety", "state": "NodeApproved"},
         {"id": "mt-node-002", "skill": "tool-inspection", "state": "Validated"}],
        {"bench-safety": ["bench-safety"], "tool-inspection": ["tool-inspection"]})


def published_with_a_stale_node() -> Verdict:
    """The legal run, with one node stale at the moment of publication.

    An earlier version of this scene was two hand-written steps. It refused —
    but for the shape of the trace, not for the staleness, and the runner below
    could not tell the difference. A scene that passes for the wrong reason is
    worse than one that fails.
    """
    run = legal_run()
    return temporal.check(mutate(run, find(run, "PublishRequested"),
                                 stale_nodes=[N1]))


# Each scene names the refusal it must produce. Without that a scene passes on
# any refusal at all — including one about the shape of its own input, which is
# how the last one here quietly stopped demonstrating what it claimed to.
SCENES = [
    ("a brief that cannot be satisfied", unsatisfiable_brief, "z3", "unsat-core"),
    ("an audience the author was not granted", audience_not_granted, "opa", "named-rule"),
    ("a node citing a source the audience cannot see", restricted_source, "datalog", "leak-path"),
    ("an objective nothing approved covers", objective_not_covered, "prolog", "proof-tree"),
    ("a course published with a stale node", published_with_a_stale_node,
     "temporal", "violated-formula"),
]


def main() -> int:
    failures = 0
    for title, scene, engine, kind in SCENES:
        try:
            verdict = scene()
        except EngineUnavailable as exc:
            print(f"  ✗ {title}\n      the engine could not run: {exc}")
            failures += 1
            continue
        if verdict.ok:
            print(f"  ✗ {title}\n      was allowed, and should not have been")
            failures += 1
            continue
        r = verdict.refusal
        if (r.engine, r.kind) != (engine, kind):
            print(f"  ✗ {title}\n      was refused by {r.engine} with a "
                  f"{r.kind}, and this scene exists to show {engine} refuse "
                  f"with a {kind}: {r.summary}")
            failures += 1
            continue
        print(f"  · {title}")
        print(f"      {r.engine} refuses with a {r.kind}: {r.summary}")
    print()
    print("every refusal carried an artifact" if not failures
          else f"{failures} scene(s) did not refuse as they must")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
