# The live run

2 October 2026. Gemini (`gemini-2.5-flash`) writes, Amazon Bedrock Guardrails
(`mt-guard`, version 1, built by `make guardrail-create` from
`fixtures/guardrail-policy.yaml`) screens, the machine decides. Account checked
before every call by `make whoami`. Three runs of `make live-run`, then two from the
course builder (`make ui`, Live), all on the same brief as `make run`.

## The guardrail on three known answers

The same in every run, and the same as `make live`:

| text | point | answer | as the recording assumes |
|---|---|---|---|
| a lesson sentence | brief-in | allow | yes |
| the forbidden-topic brief, *keeping up output when the guard is in the way* | brief-in | deny: `defeating-a-guard` | yes — refused by topic, though the title asks for nothing outright |
| a sentence carrying an email address | node-out | deny: `email` | yes |

## Run 1 — stopped, BlockedRecoverable

| attempt | what the model returned | what refused it |
|---|---|---|
| outline 1 | skills the catalog does not have: `injury-reporting`, `manual-handling` | Datalog, skills grounded |
| outline 2 | a node type outside `topic`, `exam` | JSON Schema |
| outline 3 | accepted | — |
| node 1 | a block type the catalog does not have | JSON Schema, block schemas |
| node 2, 3 | a number 64,755 digits long; the SDK could not parse the answer | read as an outage; the retry budget ended it |

The guardrail allowed every artifact; every refusal came from the layer that
owns that kind of fault. What the run showed about the gateway: its rules told
the model to use the catalog without naming it, an enum sent without a type was
ignored by Gemini, and an unreadable answer was counted as a service that went
quiet rather than a model fault. All three fixed in `85b20f9`.

## Run 2 — stopped, NodeRepair

| attempt | what the model returned | what refused it |
|---|---|---|
| outline | accepted on the first attempt | — |
| node 1 | blocks, and no duration | Z3, arithmetic: *the node has blocks and states no duration* |
| node 2 | a block carrying a field its type does not allow | JSON Schema, closed block schema |
| — | the repair budget is spent | the node waits in NodeRepair for a person |

The model had been offered every field of every block type at once. Each block
type is now its own shape, exactly its catalog row, and minutes are required
within the organisation's limit: `b79c5be`.

## Run 3 — a node written, screened and checked

```
stage  1 schema · policy            brief                       BriefValidation
stage  3 guardrail brief-in         brief                       allow
stage 10 checks 7–9 · admission     brief                       OutlineDrafting
stage  3 retrieval · rights filter  sources                     ['apprentices']
stage  4 routing                    outline                     GeminiGenerator
stage  5 generation                 outline                     gemini-2.5-flash
stage  6 guardrail outline-out      outline                     allow
stage 10 checks 7–9 · admission     outline                     OutlineReview
stage  3 retrieval · rights filter  sources                     ['apprentices']
stage  4 routing                    whfapp-topic-bench-safety   GeminiGenerator
stage  5 generation                 whfapp-topic-bench-safety   gemini-2.5-flash
stage  6 guardrail node-out         whfapp-topic-bench-safety   allow
stage 10 checks 7–9 · admission     whfapp-topic-bench-safety   Validated

revision 1: ContentInProgress · the first topic Validated, waiting for a person; five nodes Planned
```

No repair at any step. The node waits for a person, as every node does: the
model proposes, nobody but a person approves.

## Run 4 — from the course builder, sent back by the trace

`make ui`, Live. The brief went through the same gateway, now pressed by a
person on the page.

| attempt | what the model returned | what refused it |
|---|---|---|
| outline | six nodes: a topic and an exam per skill; every node's `topics` filled with learning objectives, not node ids | — accepted |
| five nodes | written, screened, checked; one repaired by Z3 | — |
| course checks | — | LTL, invariant I2: *exam generated while ['Demonstrate keeping a clear bench', …] did not stand approved* |

The exam's topics named nothing in the outline. `content_approved` counts only
topics the outline has — on purpose, so that a topic dropped from the outline
stops holding the exam — and an exam whose topics were never nodes passed it
with nothing to wait for. Invariant I2 counts every topic the exam names, and
the trace caught it at the course checks: the two disagree on a topic the
outline does not have, and the later one held.

What changed is what the model is told: an exam's topics are the ids of topic
nodes in the same outline, said in the rules and on the field. The check was
not changed. Making `references_live` treat exam topics as references was
tried and taken back: a topic dropped from the outline — an edit the
specification allows — then left an approved exam that no repair could fix,
because topics belong to the outline and not to the node. The place for the
check is the outline's own checks, before anything is generated; that is a
change to the specification, recorded in [`risks.md`](risks.md).

The page said nothing when the course checks sent the course back; it now
says why, above the structure.

## Run 5 — from the course builder, published

The same brief, with the model told what topics are. The outline came back with three topics and
one exam over `topic-bench-safety`, `topic-tool-inspection` and
`topic-dust-extraction`. Each node was written, screened by the guardrail and
checked on the first attempt; a person approved each, the course checks
passed, the approval was signed and the revision published, in 49 seconds of
calls. Every invariant held.

## What the runs show

- Nothing the model wrote reached the record unchecked. Five answers were
  refused across the runs, each by the layer the specification gives that fault
  to, each with a reason the next attempt was given; two more could not be read
  at all, and never landed.
- The fixes were all on the gateway's side of the boundary — what the model is
  told and how its answer is read. None loosened a check. Run 4 found a place
  where a guard is looser than the invariant behind it; the invariant held,
  and the gap is recorded rather than patched in the wrong place.
- The guardrail's answers matched the recording on every known case, so the
  recorded run that the rest of the evidence rests on assumes what the service
  actually does.
