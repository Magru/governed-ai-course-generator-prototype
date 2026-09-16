"""The two machines, driven by the table and nothing else.

One event is handled in a fixed order, and the order is a design decision
rather than an accident of the loop:

  1. facts the event carries are recorded (a brief, an outline, a signature);
  2. the revision machine takes its row, if it has one;
  3. each node the event is about takes its row;
  4. the revision reacts to what its nodes did — inside the same step;
  5. the step is written to the trace;
  6. the machines settle: (auto) rows run until nothing moves, each one a step
     of its own, and each followed by the revision's reactions.

Revision before node because the node rows read `course_state`: when
BlockedInputFixed unblocks a revision and its held node in one event, the node's
guard must see the revision already back in ContentInProgress. Reactions after
both, because one evaluated between 2 and 3 would re-block the revision before
its node had moved. And reactions inside the step rather than after it, because
the table keys the revision's move on the node's: a node held with no budget
and a revision still reporting itself as working is a state that never exists,
and a trace that records it for one step is refused by I14 — correctly.

An event no row accepts is refused — conformance — unless it is a broadcast,
which reaches every revision and legitimately moves none of them.
"""
from __future__ import annotations

import copy

from engines.temporal.trace import SIDE_EFFECTING

from . import bookkeeping, endpoints
from .evaluation import Evaluator
from .store import Store
from .store_guards import ServiceDown
from .transition_table import AUTO, REACTIONS, load

#: Events that are about every revision rather than one.
BROADCAST = {"PolicyChanged", "GuardrailChanged", "CatalogChanged", "KBUpdated",
             "LivePointerMoved"}
#: Events that are about every node of the revision unless one is named.
ALL_NODES = {"OutlineApproved", "BlockedInputFixed"}
SETTLE_LIMIT = 500


class MachineRefused(RuntimeError):
    """An event the tables do not permit from where the machines stand."""


class Machine:
    def __init__(self, world, config: dict, screener=None, table=None) -> None:
        self.world, self.screener = world, screener
        self.table = table or load()
        self.store = Store(config, dict(world.versions))
        self.store.readers = dict(config.get("readers") or {})
        self.current = self.store.new_revision()
        self.evaluator = Evaluator(self)
        self._depth = 0
        self._record("(initial)", {}, producer="store")

    # ── the public surface ────────────────────────────────────────────────
    def fire(self, event: str, payload: dict | None = None, *, producer="orchestrator") -> None:
        """One event, all or nothing. A refused event leaves no trace and no
        fact behind — a brief recorded by an event the machine then refused
        would be a fact nobody may act on, sitting where a guard will read it."""
        if self._depth:
            return self._fire(event, payload, producer)
        saved = copy.deepcopy((self.store, self.current.id))
        self._depth += 1
        try:
            self._fire(event, payload, producer)
        except MachineRefused:
            self.store, current = saved
            self.current = self.store.revisions[current]
            self.evaluator.forget()
            raise
        finally:
            self._depth -= 1

    def _fire(self, event: str, payload: dict | None, producer: str) -> None:
        payload = {**(payload or {}), "event": event}
        if event in SIDE_EFFECTING:
            payload.setdefault("idempotency_key", f"{event}:{len(self.store.steps)}")
        revs = self._revisions_for(event, payload)
        if event == "LivePointerMoved":
            # The pointer moves first: lost_live_pointer asks about the pointer
            # this event reports, not the one it replaced.
            self.store.live_pointer = payload["to"]
        moved, why, undecided = False, [], []
        for rev in revs:
            bookkeeping.on_event(self, "revision", rev, event, payload)
            moved |= self._take("revision", rev, event, payload, why, undecided=undecided)
            for node in self._nodes_for(rev, event, payload):
                bookkeeping.on_event(self, "node", node, event, payload)
                moved |= self._take("node", node, event, payload, why, undecided=undecided)
        if undecided and event in BROADCAST:
            # A broadcast may legitimately move nothing — but only when every
            # revision it reached was judged. One nobody could judge is not
            # "unaffected"; recording the event as if it were is fail-open.
            raise MachineRefused(f"{event} could not be decided: " + "; ".join(undecided))
        if event == "NodeEdited" and payload.get("node"):
            self._dependency_changed(revs[0], payload["node"])
        if not moved and event not in BROADCAST:
            where = ", ".join(f"revision {r.id} is {r.state}" for r in revs)
            raise MachineRefused(f"{event} is not permitted: {where}"
                                 + ("; " + "; ".join(why) if why else ""))
        for rev in revs:
            self._react(rev)
        self._record(event, payload, producer=producer)
        self.settle()

    def settle(self) -> None:
        for _ in range(SETTLE_LIMIT):
            if not self._settle_once():
                return
        raise MachineRefused("the machines did not settle: an (auto) cycle in the table")

    def trace(self) -> list[dict]:
        return [dict(s) for s in self.store.steps]

    # ── used by endpoints and bookkeeping ─────────────────────────────────
    def rev_of(self, node):
        return next(r for r in self.store.revisions.values()
                    if r.nodes.get(node.id) is node)

    def landing_state(self, obj, op) -> str:
        machine = "revision" if hasattr(obj, "approvals") else "node"
        for t in self.table[machine]:
            if t.event == op.awaited and op.issued_from in t.sources and \
                    (t.qualifier is None or "allow" in t.qualifier):
                return t.target
        raise MachineRefused(f"no row answers {op.awaited} from {op.issued_from}")

    def fork(self, rev) -> None:
        child = self.store.new_revision(forked_from=rev.id)
        for field in ("brief", "proposal", "committed_outline", "outline_version", "stamps"):
            value = getattr(rev, field)
            setattr(child, field, value.copy() if hasattr(value, "copy") else value)
        for nid, node in rev.nodes.items():
            child.nodes[nid] = bookkeeping.NodeRecord(nid, dict(node.spec), node.state,
                                                      node.content, stamps=dict(node.stamps))
        child.state = "ContentInProgress"
        self.current = child

    # ── internals ─────────────────────────────────────────────────────────
    def _revisions_for(self, event, payload):
        if event in BROADCAST:
            return list(self.store.revisions.values())
        rid = payload.get("revision")
        return [self.store.revisions[rid]] if rid else [self.current]

    def _nodes_for(self, rev, event, payload):
        if payload.get("node"):
            node = rev.nodes.get(payload["node"])
            return [node] if node else []
        return list(rev.nodes.values()) if event in ALL_NODES else []

    def _candidates(self, machine, obj, event, payload):
        for t in self.table[machine]:
            if t.event != event:
                continue
            if t.qualifier and not ({payload.get("verdict"), payload.get("layer")} & t.qualifier):
                continue
            if t.source_rule:
                if endpoints.SOURCES[t.source_rule](self, obj):
                    yield t
            elif obj.state in t.sources:
                yield t

    def _take(self, machine, obj, event, payload, why, node=None, undecided=None) -> bool:
        for t in self._candidates(machine, obj, event, payload):
            rev = obj if machine == "revision" else self.rev_of(obj)
            value, reason = self.evaluator.decide(t, rev, obj if machine == "node" else node, payload)
            if value is True:
                self._apply(t, obj, payload)
                return True
            why.append(f"{t.label()}: {reason}")
            if value is None and undecided is not None:
                undecided.append(f"{t.label()}: {reason}")
        return False

    def _apply(self, t, obj, payload) -> None:
        old = obj.state
        if t.spawn:
            bookkeeping.after_transition(self, t, obj, old, payload)
            return
        target = endpoints.TARGETS[t.target_rule](self, obj) if t.target_rule else t.target
        if isinstance(target, tuple):             # a node stopping its revision
            rev = self.rev_of(obj)
            rev_old, rev.state = rev.state, target[1]
            bookkeeping.after_transition(self, t, rev, rev_old, payload)
            return
        if target is None:
            raise MachineRefused(f"{t.label()}: {t.target_rule!r} resolves to nothing — "
                                 f"the store never recorded where {obj.id} came from")
        obj.state = target
        bookkeeping.after_transition(self, t, obj, old, payload)

    def _settle_once(self) -> bool:
        for rev in list(self.store.revisions.values()):
            if rev.awaiting_pointer:
                # PublishRequested is answered by the revision reaching
                # Published *and* by LivePointerMoved (event catalog). The
                # second is the system's to emit, not the editor's to request.
                rev.awaiting_pointer = False
                moved = {"to": rev.id}
                if rev.stale_via == "RollbackRequested":
                    moved["rolled_back_to"] = rev.id
                self.fire("LivePointerMoved", moved, producer="system")
                return True
            for node in list(rev.nodes.values()):
                if self._auto("node", node, AUTO):
                    return True
            if self._auto("revision", rev, AUTO):
                return True
        return False

    def _react(self, rev) -> None:
        """The revision's reactions to its nodes, until none holds. The
        dependency reaction is the node machine's and is fired by NodeEdited."""
        for _ in range(len(REACTIONS) + 1):
            if not any(self._take("revision", rev, reaction, {}, [])
                       for reaction in REACTIONS if reaction != "(dependency changed)"):
                return
        raise MachineRefused(f"revision {rev.id}: its reactions to its nodes do not settle")

    def _dependency_changed(self, rev, edited: str) -> None:
        for node in rev.nodes.values():
            if node.id != edited:
                self._take("node", node, "(dependency changed)", {"node": edited}, [])

    def _auto(self, machine, obj, event) -> bool:
        if event == AUTO:
            failure = self.evaluator.check_failure(machine, obj)
            if failure is not None:
                self.fire("CheckFailed", failure, producer="checks")
                return True
        rev = obj if machine == "revision" else self.rev_of(obj)
        before = (obj.state, rev.state, len(self.store.revisions))
        try:
            taken = self._take(machine, obj, event, {}, [])
        except ServiceDown:
            unreachable = {"node": obj.id} if machine == "node" else {"revision": rev.id}
            self.fire("ServiceUnreachable", unreachable, producer="gateway")
            return True
        if not taken:
            return False
        if (obj.state, rev.state, len(self.store.revisions)) == before:
            return False            # a row whose effect is already in place
        self._react(rev)
        self._record(AUTO, {"node": obj.id} if machine == "node" else {}, producer="machine")
        return True

    def _record(self, event, payload, *, producer) -> None:
        n = len(self.store.steps)
        rev = self.current
        step = {"event": event, **self.store.snapshot(rev),
                **{k: v for k, v in payload.items() if k in _PAYLOAD_KEYS and v is not None},
                "event_id": f"e{n:04d}", "event_time": f"step-{n:04d}",
                "producer": producer, "correlation_id": f"lineage-{self.store.revisions[1].id}",
                "causation_id": f"e{n - 1:04d}" if n else "e0000",
                "schema_version": "1"}
        if event in SIDE_EFFECTING:
            step["idempotency_key"] = payload.get("idempotency_key")
        self.store.steps.append(step)


_PAYLOAD_KEYS = {"node", "artifact", "node_type", "topics", "rolled_back_to"}
