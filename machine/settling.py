"""Letting the machines come to rest after an event.

After every event the machines settle: (auto) rows run until nothing moves,
each one a step of its own and each followed by the revision's reactions to
its nodes; a publication or a rollback is answered by the system moving the
pointer; a check batch that fails becomes a CheckFailed event carrying the
engine's artifact; a guardrail that does not answer becomes the Timeout row's
ServiceUnreachable. Kept apart from dispatch so each file reads as one idea.
"""
from __future__ import annotations

from .refusal import MachineRefused
from .store_guards import ServiceDown
from .transition_table import AUTO, REACTIONS

SETTLE_LIMIT = 500


class Settling:
    def settle(self) -> None:
        for _ in range(SETTLE_LIMIT):
            if not self._settle_once():
                return
        raise MachineRefused("the machines did not settle: an (auto) cycle in the table")

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
        self._record(AUTO, {"node": obj.id} if machine == "node" else {}, producer="machine", rev=rev)
        return True

