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
from .recording import Recording
from .refusal import MachineRefused  # noqa: F401 — the name callers import from here
from .settling import Settling
from .transition_table import load

#: Events that are about every revision rather than one.
#: What replaces a node's content. Its dependents are verified again.
NEW_CONTENT = {"NodeEdited", "NodeGenerated"}
BROADCAST = {"PolicyChanged", "GuardrailChanged", "CatalogChanged", "KBUpdated",
             "LivePointerMoved"}
#: Events that are about every node of the revision unless one is named.
ALL_NODES = {"OutlineApproved", "BlockedInputFixed"}


class Machine(Settling, Recording):
    def __init__(self, world, config: dict, screener=None, table=None) -> None:
        self.world, self.screener = world, screener
        self.table = table or load()
        self.store = Store(config, dict(world.versions))
        self.store.readers = dict(config.get("readers") or {})
        self.store.enrolled_learners = config.get("enrolled_learners")
        self.current = self.store.new_revision()
        self.evaluator = Evaluator(self)
        self._depth = 0
        self._record("(initial)", {}, producer="store")

    # ── the public surface ────────────────────────────────────────────────
    def fire(self, event: str, payload: dict | None = None, *, producer="orchestrator") -> None:
        """One event, all or nothing. A refused event leaves no trace and no
        fact behind — a brief recorded by an event the machine then refused
        would be a fact nobody may act on, sitting where a guard will read it.

        transitions.html §8: "an event arriving where no row matches is
        recorded and discarded". It is recorded — in the discard log, with its
        reason — and not in the trace, which is the history of transitions
        that happened. The caller is told why, because a producer that is never
        told its event went nowhere keeps sending it."""
        if self._depth:
            return self._fire(event, payload, producer)
        saved = copy.deepcopy((self.store, self.current.id))
        self._depth += 1
        try:
            self._fire(event, payload, producer)
        except bookkeeping.ApprovalOfUncheckedOutline as exc:
            self._restore(saved, event, str(exc))
            raise MachineRefused(str(exc)) from exc
        except MachineRefused as exc:
            self._restore(saved, event, str(exc))
            raise
        except Exception:
            # An engine that could not run, or a missing fact, is not a
            # discarded event — the deployment is broken — but it must leave
            # the store as it found it all the same.
            self._restore(saved)
            raise
        finally:
            self._depth -= 1

    def _restore(self, saved, event: str | None = None, reason: str = "") -> None:
        self.store, current = saved
        self.current = self.store.revisions[current]
        self.evaluator.forget()
        if event is not None:
            self.store.discarded.append({"event": event, "reason": reason,
                                         "at_step": len(self.store.steps)})

    def permits(self, event: str, payload: dict | None = None) -> tuple[bool, str]:
        """Would the tables accept this event now? Asked by running it and
        putting everything back — the membrane's legality check defers to the
        machine rather than keeping a second copy of the table."""
        saved = copy.deepcopy((self.store, self.current.id))
        self._depth += 1
        try:
            self._fire(event, payload, "membrane")
            return True, ""
        except MachineRefused as exc:
            return False, str(exc)
        finally:
            self._depth -= 1
            self.store, current = saved
            self.current = self.store.revisions[current]
            self.evaluator.forget()

    def _fire(self, event: str, payload: dict | None, producer: str) -> None:
        payload = {**(payload or {}), "event": event}
        if event in SIDE_EFFECTING:
            payload.setdefault("idempotency_key", f"{event}:{len(self.store.steps)}")
        revs = self._revisions_for(event, payload)
        self._validate_targets(event, payload, revs)
        if event == "LivePointerMoved":
            # The pointer moves first: lost_live_pointer asks about the pointer
            # this event reports, not the one it replaced.
            self.store.live_pointer = payload["to"]
        moved, why, undecided, acted = False, [], [], None
        rested_on = {rev.id: self._dependencies(rev) for rev in revs} if event == "OutlineApproved" else {}
        for rev in revs:
            bookkeeping.on_event(self, "revision", rev, event, payload)
            rev_moved = self._take("revision", rev, event, payload, why, undecided=undecided)
            if rev_moved:
                moved, acted = True, acted or rev
            # An event about the whole revision moves its nodes only if the
            # revision took it: an OutlineApproved the revision refused must not
            # remove nodes on the strength of an outline nobody committed.
            if event in ALL_NODES and not rev_moved and event != "BlockedInputFixed":
                continue
            for node in self._nodes_for(rev, event, payload):
                before = node.state
                bookkeeping.on_event(self, "node", node, event, payload)
                if self._take("node", node, event, payload, why, undecided=undecided):
                    moved, acted = True, acted or rev
                    if node.state == "Removed" and before != "Removed":
                        self._dependency_changed(rev, node.id)
        if undecided and event in BROADCAST:
            # A broadcast may legitimately move nothing — but only when every
            # revision it reached was judged. One nobody could judge is not
            # "unaffected"; recording the event as if it were is fail-open.
            raise MachineRefused(f"{event} could not be decided: " + "; ".join(undecided))
        if event in NEW_CONTENT and payload.get("node"):
            # Edited means the node's content was replaced, by a person or by a
            # regeneration. Cascading on the person's edit alone let a dependent
            # be approved against content that a repair then replaced, and the
            # course went to review with the exam never checked against it.
            self._dependency_changed(revs[0], payload["node"])
        for rev in revs:
            if rev.id in rested_on:
                self._dependencies_added(rev, rested_on[rev.id])
        if not moved and event not in BROADCAST:
            where = ", ".join(f"revision {r.id} is {r.state}" for r in revs)
            said = f" ({payload['layer']}: {payload['reason']})" if payload.get("layer") else ""
            raise MachineRefused(f"{event}{said} is not permitted: {where}"
                                 + ("; " + "; ".join(why) if why else ""))
        for rev in revs:
            self._react(rev)
        self._record(event, payload, producer=producer, rev=acted or self._subject(payload))
        self.settle()

    def _validate_targets(self, event, payload, revs) -> None:
        """An event that names something must name something that exists, and
        a pointer may only be moved onto a revision learners may be served."""
        if payload.get("revision") is not None and payload["revision"] not in self.store.revisions:
            raise MachineRefused(f"{event} names revision {payload['revision']}, which does not exist")
        if payload.get("node") and not any(payload["node"] in r.nodes for r in revs):
            raise MachineRefused(f"{event} names node {payload['node']}, which this revision does not have")
        if event == "LivePointerMoved":
            target = self.store.revisions.get(payload.get("to"))
            if target is None or target.state != "Published":
                raise MachineRefused(f"the pointer cannot move to revision {payload.get('to')}: "
                                     f"it is {getattr(target, 'state', 'absent')}, not Published")

    def _subject(self, payload):
        rid = payload.get("to") or payload.get("revision")
        return self.store.revisions.get(rid, self.current)

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
            setattr(child, field, copy.deepcopy(getattr(rev, field)))
        for nid, node in rev.nodes.items():
            child.nodes[nid] = bookkeeping.NodeRecord(nid, copy.deepcopy(node.spec), node.state,
                                                      copy.deepcopy(node.content),
                                                      stamps=dict(node.stamps),
                                                      checked_stamps=dict(node.checked_stamps))
            if node.state in ("NodeApproved", "Validated") and any(
                    self.store.current[k] != v for k, v in node.checked_stamps.items()):
                # A fork starts under the rules in force. The revision it came
                # from may keep old stamps while nobody edits it; this one will
                # be edited, and what it inherits checked under a replaced
                # version is checked again before anyone can publish it.
                child.nodes[nid].state = "NeedsRevalidation"
            if nid in rev.screened:
                # The fork carries the node's content, so it carries the verdict
                # on that content — and the version that gave it. A verdict on
                # the revision as a whole is not carried: the fork will differ.
                child.screened[nid] = dict(rev.screened[nid])
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
        # A configuration change reaches every node: a draft's checked nodes are
        # checked again, and the rows say which — a published revision's none.
        return list(rev.nodes.values()) if event in ALL_NODES | BROADCAST else []

    def _candidates(self, machine, obj, event, payload):
        for t in self.table[machine]:
            if t.event != event:
                continue
            if t.qualifier and not ({payload.get("verdict"), payload.get("layer")} & t.qualifier):
                continue
            if t.target_rule and endpoints.TARGETS[t.target_rule] is endpoints.TARGETS.get(
                    "course → BlockedRecoverable") and self.rev_of(obj).state != "ContentInProgress":
                # The revision table stops a revision for its nodes only from
                # ContentInProgress. A node row stopping a revision that is in
                # review, archived or re-checking its outline is not a row.
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

