"""Permission, answered by OPA and nobody else.

The binary is called as a subprocess. That is the point: if it is missing, this
raises, and the run stops. An earlier reference implementation shipped a Python
mirror of the same rules and fell back to it when the binary was absent — which
means the deployment could pass every test while never once consulting the
policy engine it claims to run on.
"""
from __future__ import annotations
import json, pathlib, shutil, subprocess

from ..contract import (EngineUnavailable, RefusalWithoutArtifact, Verdict,
                        allowed, refused)

HERE = pathlib.Path(__file__).parent
POLICY = HERE / "policy.rego"
ENGINE = "opa"


def check(action: str, actor: dict, brief: dict, course_state: str, org: dict) -> Verdict:
    """May this actor take this action, over this audience, in this state?"""
    input_doc = {"action": action, "actor": actor, "brief": brief, "course_state": course_state}
    data = {"org": org}

    with _tempdata(data) as data_path:
        allow = _eval("data.course.policy.allow", input_doc, data_path)
        if allow is True:
            return allowed(engine=ENGINE, rule="allow")
        denials = _eval("data.course.policy.deny", input_doc, data_path) or []

    if not denials:
        # The policy said no and gave no reason. Inventing one here would put a
        # Python string where an engine's verdict belongs — the caller would read
        # "the policy denied because…" about a sentence the policy never wrote.
        # Every way of failing is supposed to have a `deny` clause; that one does
        # not is a hole in the policy, and a hole is not a refusal.
        raise RefusalWithoutArtifact(
            "the policy refused without naming a rule. Add a deny clause for "
            f"this case: action={action!r}, state={course_state!r}")
    first = denials[0]
    return refused(
        kind="named-rule",
        summary=f"{first['rule']}: {first['message']}",
        detail=denials,
        engine=ENGINE)


import contextlib, os, tempfile


@contextlib.contextmanager
def _tempdata(data: dict):
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        yield path
    finally:
        os.unlink(path)


def _eval(query: str, input_doc: dict, data_path: str):
    if shutil.which("opa") is None:
        raise EngineUnavailable(
            "the opa binary is not on PATH. There is no Python fallback here on "
            "purpose: a mirror of these rules would make 'the policy engine ran' "
            "unprovable at exactly the moment it mattered.")
    try:
        proc = subprocess.run(
            ["opa", "eval", "--format", "json",
             "--data", str(POLICY), "--data", data_path,
             "--stdin-input", query],
            input=json.dumps(input_doc), capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EngineUnavailable(f"opa did not run: {exc}") from exc
    if proc.returncode != 0:
        raise EngineUnavailable(f"opa exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    results = json.loads(proc.stdout).get("result") or []
    return results[0]["expressions"][0]["value"] if results else None
