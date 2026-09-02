# Model package

The seven specification pages one directory up are prose: they argue. These files
are the same system in a form something other than a person can read — a diff, a
linter, a simulator.

Each file answers one question, names an owner, and says what event should make
someone revise it. That is the whole convention.

| File | Answers | Maintained |
|---|---|---|
| [`system-definition.yaml`](system-definition.yaml) | What does the system promise? | by hand |
| [`functional-model.yaml`](functional-model.yaml) | What does it do? | by hand |
| [`context-diagram.mmd`](context-diagram.mmd) | Who is inside the boundary, who is outside? — [rendered](diagrams.md#context) | by hand |
| [`state-inventory.yaml`](state-inventory.yaml) | What does it remember, who is authoritative, how is it recovered? | by hand, **linted** |
| [`event-catalog.yaml`](event-catalog.yaml) | What happened, and who may claim it? | by hand, **linted** |
| [`transitions.yaml`](transitions.yaml) | What is permitted in each state? | exported |
| [`state-machine-revision.mmd`](state-machine-revision.mmd) · [`state-machine-node.mmd`](state-machine-node.mmd) | the same, as pictures — [rendered](diagrams.md) | exported |
| [`failure-scenarios.yaml`](failure-scenarios.yaml) | How do we fail safely? | exported |
| [`invariants.yaml`](invariants.yaml) | What must be true of every trace, and what does each rule forbid? | by hand, **linted** |
| [`assumptions.yaml`](assumptions.yaml) | What does the model depend on, and how would we notice it stopped being true? | by hand |
| [`latency-budget.yaml`](latency-budget.yaml) | Can the path meet a deadline, and how many editors fit? | by hand |

**Nine of the framework's twenty artifacts**, and all ten items of its Minimum Viable
System Model — plus `invariants.yaml`, which the framework's list does not contain and
without which this system cannot be modelled: it carries the fifteen temporal properties
the architecture exists to guarantee. The eleven that remain are the production-ready half — a
deployment model, an executable simulation, a wired monitoring map, a traceability
linter — and the [system model page](../modeling.html) grades every one.

## Regenerating and checking

```
python3 export-model.py
```

Two jobs. It **generates** the transition table, the two state-machine diagrams
and the failure scenarios from the tables in `../states.html`,
`../transitions.html` and `../safety.html`. It **lints** the two hand-maintained
files that mirror those tables: every state and every event name on the pages must
appear in `state-inventory.yaml` and `event-catalog.yaml`, or it writes nothing and
says which name went missing.

That is why the `updated_when` line in each header is a command rather than a
promise. A row added to a page and forgotten here fails the run.

## What building this found

Moving the tables into files surfaced six things the prose had been absorbing.
None is cosmetic; each is a question the specification does not answer.

1. **`BlockedFinal` exists in both machines** with different exits. Any tool
   reading state names unqualified will conflate them.
2. **Seven transition endpoints are not state names** — *the state that blocked*,
   *any state in the live lineage*, *the state after the operation*. Each needs a
   resolution rule before this package can drive a simulation. They are listed
   under `open_questions` in `transitions.yaml`.
3. **One node transition never says where the node goes.** `NodeRepair` on an
   exhausted retry budget records `course → BlockedRecoverable` — what happens to
   the *course*. The node's own target is unstated.
4. **`·` is overloaded.** In `ContentInProgress · BlockedRecoverable` it means
   *either*; in `rev n+1 · ContentInProgress` it qualifies a different revision.
   A reader infers which. A parser cannot.
5. **Two node transitions reached a state the node machine did not have.** A timeout
   while drafting, or an unreachable guardrail, sent a node to `ErrorRecovery` — a
   *revision* state. Nothing declared it for nodes and nothing left it. **Fixed
   02.09.2026:** the node machine now has its own `NodeRecovery`, `recovery_from`
   records which stage failed, and three exits return it — to generation, to the
   guardrail, or to a person once the retry budget is spent. The linter fails on any
   new leak of this kind.
6. **No event declares an envelope.** `event-catalog.yaml` now specifies the one
   every event must acquire, and says what breaks when each field is missing.
   Nothing emits it yet.

## What the numbers say

From `latency-budget.yaml`, all estimates and all resting on `unknowns` in
`system-definition.yaml`:

- Every check this architecture adds costs **412 ms against a twelve-second model
  call — 3.2 % of the path**. Governance is not the bottleneck. The path fits a
  proposed thirty-second target with **12.6 s left for queueing and tail**.
- A node takes **17 s to produce and about 180 s to review**. The human is the
  bottleneck by roughly a factor of ten, which is the intended outcome.
- One model worker carries about **eight concurrent editors** at a safe utilisation —
  saturation is 11.35 editors per worker; eight is that with headroom.
- The staleness cascade **does not regenerate**: five hundred stale nodes re-verify in
  under three minutes of compute — but every one it surfaces for a person is three
  minutes of review, so the same five hundred are about **25 hours of editor attention**.

## Owners

Ten distinct owners across the state inventory — the state store, the platform,
the policy bundle, the guardrail service, the gateway, the editor. The file
headers still say `system architect`, which is honest for a one-person project and
useless as governance; the framework asks for an owner precisely so a stale
artifact has someone to go stale on.
