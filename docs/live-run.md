# The live run

2 October 2026. Gemini (`gemini-2.5-flash`) writes, Amazon Bedrock Guardrails
(`mt-guard`, version 1, built by `make guardrail-create` from
`fixtures/guardrail-policy.yaml`) screens, the machine decides. Account checked
before every call by `make whoami`. Three runs of `make live-run`, the same brief
as `make run`, with nothing changed between them but the gateway's code.

## The guardrail on three known answers

The same in all three runs, and the same as `make live`:

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

## What the three runs show

- Nothing the model wrote reached the record unchecked. Five answers were
  refused across the runs, each by the layer the specification gives that fault
  to, each with a reason the next attempt was given; two more could not be read
  at all, and never landed.
- The fixes were all on the gateway's side of the boundary — what the model is
  told and how its answer is read. None loosened a check.
- The guardrail's answers matched the recording on every known case, so the
  recorded run that the rest of the evidence rests on assumes what the service
  actually does.
