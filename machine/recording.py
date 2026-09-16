"""Writing one step of the trace, in the shape trace-schema.yaml declares."""
from __future__ import annotations

from engines.temporal.trace import SIDE_EFFECTING

_PAYLOAD_KEYS = {"node", "artifact", "node_type", "topics", "rolled_back_to"}


class Recording:
    def _record(self, event, payload, *, producer, rev=None) -> None:
        n = len(self.store.steps)
        rev = rev or self.current            # the revision the step is about
        step = {"event": event, **self.store.snapshot(rev),
                **{k: v for k, v in payload.items() if k in _PAYLOAD_KEYS and v is not None},
                "event_id": f"e{n:04d}", "event_time": f"step-{n:04d}",
                "producer": producer, "correlation_id": f"lineage-{self.store.revisions[1].id}",
                "causation_id": f"e{n - 1:04d}" if n else "e0000",
                "schema_version": "1"}
        if event == "NodeGenerated" and payload.get("node") in rev.nodes:
            # I2 reads what kind of node was generated and what it tests; the
            # outline already says, so the step carries it rather than trusting
            # a caller to restate it.
            spec = rev.nodes[payload["node"]].spec
            step["node_type"] = spec.get("type")
            if spec.get("topics"):
                step["topics"] = list(spec["topics"])
        if event in SIDE_EFFECTING:
            step["idempotency_key"] = payload.get("idempotency_key")
        self.store.steps.append(step)


