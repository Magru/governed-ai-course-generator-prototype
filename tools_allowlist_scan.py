#!/usr/bin/env python3
"""Every name under fixtures/ must come from the invented universe.

A denylist catches the customer names someone remembered. This catches what they
did not: a real identifier pasted from a database, a competency model copied
across, a title in a language no fictional company speaks. It also keeps the list
of real tenants out of a public repository, where a denylist would have published
exactly what it exists to protect.

Exit 1 on the first unknown token. Run it before any fixture exists, and it
passes; run it on the canary, and it must fail.
"""
from __future__ import annotations
import pathlib, re, sys, yaml

ROOT = pathlib.Path(__file__).parent
FIXTURES = ROOT / "fixtures"
NAMESPACE = FIXTURES / "namespace.yaml"

# Things that look like a name someone could have copied from somewhere real.
# A bare lowercase word counts too. The first version of this regex required a
# hyphen or an underscore, which made every customer slug — a single lowercase
# word — invisible to the scan that exists to catch exactly those.
# Anchored at word boundaries so a compound is matched whole. Without the
# anchor, "max_nodes_per_course" was read as "nodes_per_course" — the
# declared name never matched, and declaring it again would not have helped.
TOKEN = re.compile(r"\b[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+\b"
                   r"|\b[a-z][a-z0-9]{3,}\b"
                   r"|\b[A-Z][a-zA-Z]{2,}\b")
PROPER = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
HEBREW = re.compile(r"[֐-׿]")

# YAML keys and structural words are ours, not data.
# Words that describe the *shape* of a fixture rather than its content: YAML
# keys, JSON Schema vocabulary, and the handful of English words that open a
# sentence in a comment. Domain words do not belong here — they belong in
# namespace.yaml, where declaring one is the point.
STRUCTURAL = {
    # keys
    "organisation", "people", "audiences", "skills", "block_types", "blocks",
    "generic", "kb_namespace", "course_namespace", "knowledge_base", "catalog",
    "chunks", "thresholds", "slug", "name", "domain", "about", "role", "label",
    "id", "title", "objectives", "audience", "state", "type", "version",
    "chunk", "text", "source", "visible", "settings", "brief", "nodes", "node",
    "may_author_for", "visible_to", "requires_visual_review", "repair_budget",
    "max_nodes_per_course", "max_minutes_per_lesson", "max_audience_breadth",
    "minutes_per_lesson", "nodes_per_course", "audience_breadth", "action",
    "actor", "course", "artifact", "invariant", "state", "skill", "cites",
    "expect", "reason", "refused_by", "cites", "src", "alt", "caption",
    "question", "options", "answer", "points", "items", "heading", "paragraph",
    "image", "checklist", "quiz", "callout", "minutes", "topics", "exam",
    # JSON Schema
    "schema", "object", "string", "integer", "array", "boolean", "number",
    "properties", "required", "enum", "format", "const",
    # sentence openers used in the comments of this repository
    "true", "false", "null", "and", "the", "for", "with", "not", "one", "two",
    "what", "that", "this", "these", "those", "every", "keep", "check", "set",
    "hone", "connect", "wear", "report", "lift", "a", "an", "it", "its",
}


def vocabulary(namespace: pathlib.Path = NAMESPACE) -> set[str]:
    ns = yaml.safe_load(namespace.read_text(encoding="utf-8"))
    words: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                words.add(str(k).lower())
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif node is not None:
            for part in re.split(r"[\s,]+", str(node)):
                if part:
                    words.add(part.lower())

    walk(ns)
    # A compound like "meridian-tools" licenses its parts, and a plural key
    # licenses its singular — otherwise "skills:" in the namespace fails to
    # cover "skill:" in a fixture, and the first such mismatch is where someone
    # starts weakening the scan instead of declaring the word.
    for w in list(words):
        words.update(p for p in re.split(r"[-_.]", w) if p)
    for w in list(words):
        if len(w) > 3 and w.endswith("s"):
            words.add(w[:-1])
    # A fixture may name any state the specification declares. Those names are
    # the model's, not this file's, and repeating them here would be a second
    # copy to keep in step.
    inventory = ROOT / "model" / "state-inventory.yaml"
    if inventory.exists():
        model = yaml.safe_load(inventory.read_text(encoding="utf-8"))
        for variable in model.get("variables", []):
            values = variable.get("valid_values")
            if isinstance(values, list):
                words.update(str(v).lower() for v in values)
    return words | STRUCTURAL


def _has_declared_prefix(token: str, prefixes: list[str]) -> bool:
    """mt-kb-001 is licensed by the mt-kb prefix; mtkb-001 is not."""
    return any(token == p or token.startswith(p + "-") for p in prefixes)


def scan(root: pathlib.Path = FIXTURES,
         namespace: pathlib.Path | None = None) -> list[str]:
    if not root.exists():
        return [f"{root} does not exist"]
    known = vocabulary(namespace or NAMESPACE)
    prefixes = yaml.safe_load((namespace or NAMESPACE).read_text(encoding="utf-8")).get("id_prefixes") or []
    problems: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "namespace.yaml":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root.parent) if root.parent in path.parents else path.name
        for m in UUID.finditer(text):
            problems.append(f"{rel}: a real-looking UUID — {m.group(0)}")
        if HEBREW.search(text):
            problems.append(f"{rel}: Hebrew text — no fictional company here speaks it")
        # Knowledge-base chunks contain ordinary English, and demanding that
        # every common word be declared would make the vocabulary unreadable and
        # the scan the first thing anyone weakened. So prose is held to a
        # narrower rule: only its proper nouns must be ours. A borrowed name is
        # a proper noun; "the guard must be closed before starting" is not.
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            key, sep, value = line.partition(":")
            # A comment, or a line with no key at all, is prose. Only a short
            # value after a key is treated as an identifier.
            prose = (stripped.startswith("#") or not sep
                     or stripped.startswith("- ") and not sep
                     or len(value.split()) > 3)
            pattern = PROPER if prose else TOKEN
            for m in pattern.finditer(line):
                token = m.group(0)
                if token.lower() in known:
                    continue
                if all(p in known for p in re.split(r"[-_]", token.lower()) if p):
                    continue
                if _has_declared_prefix(token.lower(), prefixes):
                    continue
                kind = "proper noun in prose" if prose else "identifier"
                problems.append(
                    f"{rel}:{number}: {token!r} is not in the invented universe ({kind})")
    return problems


if __name__ == "__main__":
    found = scan()
    if found:
        print("LEAK SCAN FAILED — a name that is not ours reached fixtures/:", file=sys.stderr)
        for p in found[:40]:
            print(f"  ✗ {p}", file=sys.stderr)
        if len(found) > 40:
            print(f"  … and {len(found) - 40} more", file=sys.stderr)
        raise SystemExit(1)
    print("leak scan: every name under fixtures/ belongs to the invented universe")
