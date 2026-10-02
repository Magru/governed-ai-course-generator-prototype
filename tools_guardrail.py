#!/usr/bin/env python3
"""The Bedrock guardrail, built from fixtures/guardrail-policy.yaml.

The compliance officer's policy is the fixture; this turns it into the request
Bedrock takes, so what the service enforces is what the repository says, not
what someone clicked. Without --create it only prints the request.

    make guardrail          print the CreateGuardrail request; nothing is sent
    make guardrail-create   create it, publish version 1, print the .env lines

Creating goes through gateway/provider/bedrock.py like every other AWS call, so
it checks which account it is in before it does anything.
"""
from __future__ import annotations

import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

POLICY = ROOT / "fixtures" / "guardrail-policy.yaml"
# Bedrock names the personal data it recognises; a kind it has no name for is
# described by a pattern instead.
PII_TYPES = {"email": "EMAIL", "phone": "PHONE"}
PII_PATTERNS = {"national-id": (r"\b\d{9}\b", "a nine-digit national identity number")}
REFUSED = "This request was stopped by the organisation's content policy."


def _filter(f: dict) -> dict:
    """One content filter. A filter that screens input only — a prompt attack
    is something said to a model, not something a model says — has no output
    strength, which Bedrock spells NONE."""
    strength = f["strength"].upper()
    modalities = [m.upper() for m in f["modalities"]]
    input_only = f.get("screens") == "input-only"
    return {"type": f["type"].upper().replace("-", "_"),
            "inputStrength": strength, "outputStrength": "NONE" if input_only else strength,
            "inputModalities": modalities, "outputModalities": modalities}


def request() -> dict:
    g = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["guardrail"]
    unknown = [p for p in g["personal_data"] if p not in PII_TYPES | PII_PATTERNS]
    if unknown:
        raise SystemExit(f"no Bedrock mapping for personal data {unknown}: add one here")
    return {
        "name": g["id"],
        "description": f"{g['id']} as published by {g['owner']}, from fixtures/guardrail-policy.yaml",
        "topicPolicyConfig": {"topicsConfig": [
            {"name": t["id"], "definition": " ".join(t["definition"].split()), "type": "DENY"}
            for t in g["denied_topics"]]},
        "sensitiveInformationPolicyConfig": {
            "piiEntitiesConfig": [{"type": PII_TYPES[p], "action": "BLOCK"}
                                  for p in g["personal_data"] if p in PII_TYPES],
            "regexesConfig": [{"name": p, "description": PII_PATTERNS[p][1],
                               "pattern": PII_PATTERNS[p][0], "action": "BLOCK"}
                              for p in g["personal_data"] if p in PII_PATTERNS]},
        "contentPolicyConfig": {"filtersConfig": [_filter(f) for f in g["content_filters"]]},
        "blockedInputMessaging": REFUSED,
        "blockedOutputsMessaging": REFUSED,
    }


def create() -> int:
    from gateway.provider.bedrock import client
    control = client("bedrock")
    made = control.create_guardrail(**request())
    version = control.create_guardrail_version(
        guardrailIdentifier=made["guardrailId"],
        description="published from fixtures/guardrail-policy.yaml")
    print("created. Add these two lines to .env:\n")
    print(f"BEDROCK_GUARDRAIL_ID={made['guardrailId']}")
    print(f"BEDROCK_GUARDRAIL_VERSION={version['version']}")
    return 0


def main(argv: list[str]) -> int:
    if "--create" in argv:
        return create()
    print(json.dumps(request(), indent=2, ensure_ascii=False))
    print("\nnothing was sent. make guardrail-create sends it.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
