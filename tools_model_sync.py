#!/usr/bin/env python3
"""Vendor the specification's model package at a tag, and lock what was taken.

The prototype loads its state machine from these files. If they drift from the
published specification, the claim that the specification *is* the program stops
being true — so the lock is checked in CI and a mismatch fails the build.

The hash is of a canonical form: the YAML parsed, keys sorted, and the generated
date dropped. The exporter stamps today's date into every artifact, so hashing
raw bytes would report drift every time it ran with nothing changed.
"""
from __future__ import annotations
import hashlib, json, pathlib, re, sys, urllib.request

ROOT = pathlib.Path(__file__).parent
MODEL = ROOT / "model"
LOCK = ROOT / "model.lock"
REPO = "Magru/governed-ai-course-generator"
FILES = ["system-definition.yaml", "functional-model.yaml", "context-diagram.mmd",
         "state-inventory.yaml", "transitions.yaml", "guards.yaml",
         "event-catalog.yaml", "invariants.yaml", "trace-schema.yaml",
         "failure-scenarios.yaml",
         "assumptions.yaml", "latency-budget.yaml", "state-machine-revision.mmd",
         "state-machine-node.mmd", "diagrams.md", "README.md"]


def canonical(name: str, text: str) -> str:
    """Everything the file says, minus the day it was written.

    An earlier version hashed the parsed YAML instead. That ignored comments —
    and in these artifacts the comments carry the reasoning: why a guard exists,
    what breaks without a field, which earlier draft was wrong. A lock that lets
    all of that change silently is not protecting the thing worth protecting.
    Only the two date stamps are stripped, because the exporter rewrites them on
    every run and they would report drift with nothing changed.
    """
    lines = [ln for ln in text.splitlines()
             if not re.match(r'\s*(generated|authored):', ln)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def fetch(tag: str, name: str) -> str:
    url = f"https://raw.githubusercontent.com/{REPO}/{tag}/model/{name}"
    with urllib.request.urlopen(url, timeout=30) as r:      # noqa: S310 — fixed host
        if r.status != 200:
            raise SystemExit(f"{name}: HTTP {r.status} at {tag}")
        return r.read().decode("utf-8")


def sync(tag: str) -> None:
    MODEL.mkdir(exist_ok=True)
    lock = {"tag": tag, "repo": REPO, "files": {}}
    for name in FILES:
        text = fetch(tag, name)
        (MODEL / name).write_text(text, encoding="utf-8")
        lock["files"][name] = canonical(name, text)
    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"vendored {len(FILES)} artifacts at {tag}")


def verify(remote: bool = False) -> int:
    if not LOCK.exists():
        print("model.lock is missing — run `make model-sync`", file=sys.stderr)
        return 1
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    bad = []
    for name, want in lock["files"].items():
        local = MODEL / name
        if not local.exists():
            bad.append(f"{name}: vendored copy is missing")
            continue
        got = canonical(name, local.read_text(encoding="utf-8"))
        if got != want:
            bad.append(f"{name}: local copy differs from {lock['tag']}")
        if remote:
            # A different question from the one above: not "has our copy
            # changed" but "has the tag we pinned been moved under us". It needs
            # the network, so it is not what `make test` runs.
            try:
                upstream = canonical(name, fetch(lock["tag"], name))
            except Exception as exc:                    # noqa: BLE001
                bad.append(f"{name}: could not re-fetch {lock['tag']}: {exc}")
                continue
            if upstream != want:
                bad.append(f"{name}: the tag {lock['tag']} itself has moved")
    if bad:
        print("MODEL DRIFT — the prototype is not running the published specification:",
              file=sys.stderr)
        for b in bad:
            print(f"  ✗ {b}", file=sys.stderr)
        return 1
    where = "the tag" if remote else "the lock"
    print(f"model: {len(lock['files'])} artifacts match {where} ({lock['tag']})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        raise SystemExit(verify(remote="--remote" in sys.argv))
    arg = sys.argv[1] if len(sys.argv) > 1 else "spec-v2.4"
    if arg.startswith("-"):   # otherwise a mistyped flag is fetched as a tag
        raise SystemExit(f"unknown option {arg!r}; usage: tools_model_sync.py [tag | verify [--remote]]")
    sync(arg)
