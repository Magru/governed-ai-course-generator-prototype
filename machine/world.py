"""What the guards reason over that the machine does not own.

The organisation, its catalog, its knowledge base and its thresholds come from
the platform. In the prototype they come from `fixtures/`, loaded once, in the
shapes the engines already take — so a guard adapter only picks, never
reshapes, and the engines see the same facts the phase-02 tests gave them.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


def _load(name: str) -> dict:
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class World:
    org: dict
    people: dict
    thresholds: dict
    catalog: dict
    articles: list
    visibility: dict
    block_types: list
    versions: dict

    @property
    def policy_data(self) -> dict:
        """The document OPA evaluates against — grants, thresholds, approval."""
        return {"grants": {pid: {"may_author_for": p["may_author_for"]}
                           for pid, p in self.people.items()},
                "thresholds": self.thresholds,
                "approval": self.org_approval}

    @property
    def org_approval(self) -> dict:
        return self.org["approval"]

    @property
    def skills(self) -> list[str]:
        return [s["id"] for s in self.catalog["skills"]]

    @property
    def develops(self) -> dict[str, list[str]]:
        # An objective in a brief is named by the skill that closes it. The
        # catalog has no richer mapping to offer, and inventing one here would
        # be a second catalog.
        return {skill: [skill] for skill in self.skills}


def load() -> World:
    org = _load("organisation.yaml")
    kb = _load("kb.yaml")
    catalog = _load("catalog.yaml")["catalog"]
    return World(
        org=org,
        people={p["id"]: p for p in org["people"]},
        thresholds=org["thresholds"],
        catalog=catalog,
        articles=kb["articles"],
        visibility={k: v for k, v in kb["resolved_visibility"].items() if k != "source"},
        block_types=[b["id"] for b in catalog["blocks"]],
        versions={"policy": "pol-1", "guardrail": "guard-1",
                  "catalog": catalog["version"],
                  "kb": kb["knowledge_base"]["version"]},
    )
