"""Coverage, and the reason — the layer that answers "why".

`\\+` here is negation as failure, not classical negation: `uncovered` holds when
the search for a covering node *fails*, which is a statement about what this
program can prove rather than about the world. That is the right reading for a
course — an objective is uncovered when nothing in the course demonstrably
covers it — and it is why the query is narrow: over an open world the answer
would only mean "not found here".

swipl runs as a subprocess. As with OPA there is no Python path that computes
the same answer, because a fallback makes "Prolog ran" unprovable.
"""
from __future__ import annotations
import os, pathlib, re, shutil, subprocess, tempfile

from ..contract import EngineUnavailable, Verdict, allowed, refused

HERE = pathlib.Path(__file__).parent
PROGRAM = HERE / "coverage.pl"
ENGINE = "prolog"


def _atom(value: str) -> str:
    """Anything with a hyphen has to be quoted, and every id here has one."""
    return "'" + str(value).replace("'", "\\'") + "'"


def check_coverage(course_id: str, objectives: list[str], nodes: list[dict],
                   develops: dict[str, list[str]]) -> Verdict:
    if shutil.which("swipl") is None:
        raise EngineUnavailable(
            "swipl is not on PATH. No Python path computes this instead: a "
            "fallback would make 'Prolog answered' unprovable.")

    facts = [f"requires({_atom(course_id)}, {_atom(o)})." for o in objectives]
    for node in nodes:
        facts.append(f"contains({_atom(course_id)}, {_atom(node['id'])}).")
        if node.get("state") == "NodeApproved":
            facts.append(f"approved({_atom(node['id'])}).")
        if node.get("skill"):
            facts.append(f"teaches({_atom(node['id'])}, {_atom(node['skill'])}).")
    for skill, objs in develops.items():
        for objective in objs:
            facts.append(f"develops({_atom(skill)}, {_atom(objective)}).")

    goal = (
        f"forall(why_uncovered({_atom(course_id)}, O, E), (print(E), nl)), halt."
    )
    # Facts go in a file rather than down stdin: swipl consults the files it is
    # given and leaves stdin to the program, so facts piped in were never loaded
    # and every predicate came back unknown.
    declarations = (":- dynamic requires/2, contains/2, approved/1, "
                    "teaches/2, develops/2.\n")
    with tempfile.NamedTemporaryFile("w", suffix=".pl", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(declarations + "\n".join(facts) + "\n")
        facts_path = fh.name
    try:
        proc = subprocess.run(
            ["swipl", "-q", "-g", goal, "-t", "halt", str(PROGRAM), facts_path],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineUnavailable(f"swipl did not run: {exc}") from exc
    finally:
        os.unlink(facts_path)
    if proc.returncode != 0:
        raise EngineUnavailable(f"swipl exited {proc.returncode}: {proc.stderr.strip()[:300]}")

    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("explanation(")]
    if not lines:
        return allowed(engine=ENGINE, objectives=len(objectives))

    tree = [_parse(ln) for ln in lines]
    first = tree[0]
    reason = {"no_node_teaches_it": "no node in this course teaches it",
              "taught_but_not_approved": "a node teaches it, and nobody has approved that node"}
    return refused(
        kind="proof-tree",
        summary=(f"{first['objective']} is not covered: "
                 f"{reason.get(first['reason'], first['reason'])}"),
        detail=tree,
        engine=ENGINE)


def _parse(line: str) -> dict:
    """swipl prints the term it found. Keeping the printed form beside the parsed
    one means the proof stored in an audit is the proof the engine produced, not
    a re-rendering of it."""
    inner = line[len("explanation("):-1]
    objective = inner.split(",", 1)[0].strip().strip("'")
    reason = inner.rsplit(",", 1)[1].strip().rstrip(")").strip()
    partial = not re.search(r",\s*\[\s*\]\s*,\s*[a-z_]+\)?$", inner)
    return {"objective": objective, "reason": reason,
            "has_partial_match": partial, "raw": line}
