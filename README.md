# Governed AI Course Generator — prototype

The runnable half of a specification published at
**[magru.github.io/governed-ai-course-generator](https://magru.github.io/governed-ai-course-generator/)**.

A model writes a training course, node by node, from an author's brief and an
organisation's knowledge base. It never decides anything. Every step it takes is
a transition in a state machine, every transition has guards, and each guard is
answered by the engine that owns that kind of question: OPA for permission, Z3
for whether a brief can be satisfied at all, Datalog for grounding and rights,
Prolog for coverage, JSON Schema for shape, and temporal logic over the whole
trace. A managed guardrail screens what goes in and what comes out. A person
approves; the model only proposes.

The specification is not documentation about this code. It is this code's input:
the state machine is loaded from `model/transitions.yaml`, the properties it must
satisfy from `model/invariants.yaml`, and `make model-verify` fails the build if
the vendored copy has drifted from the published tag (`spec-v2.15`).

## Run it

You need Python 3.13 or newer, and two engines that are not pip packages:

```bash
brew install opa swi-prolog            # Debian/Ubuntu: the opa binary, and apt install swi-prolog-nox
```

Then:

```bash
make setup     # a virtualenv and the Python dependencies; the one step that needs the network
make test      # every test; no AWS account, no API key, no network
make run       # one course through the gateway, brief to rollback, then the seven refusal fixtures
```

Nothing above reaches outward. The model and the guardrail are replaced by
recordings behind the same two ports the live adapters use, so the run goes
through every stage a live one does, and gives the same answer every time.
Everything belongs to an invented organisation under `fixtures/`.

| target | what you see |
|---|---|
| `make run` | the course, stage by stage through the gateway: an outline repaired for a skill the catalog lacks, a node repaired for citing a source its audience cannot see, a timeout retried under the same key, publication, a notice to learners, a rollback; then the seven refusal fixtures, each stopping where the specification says |
| `make refusals` | the five refusals, each from the engine that owns it, each with its artifact: an unsat core, a named policy rule, a leak path, a proof tree, a violated formula |
| `make walkthrough` | the specification's `walkthrough.html`, step by step, reproduced by the machine |
| `make cascade` | what one edit costs at course scale — in re-checks, compute, and hours of human review — and a proof that the cascade settles |
| `make test-matrix` | regenerates [`docs/test-matrix.md`](docs/test-matrix.md) from a test run |
| `make examples` | regenerates [`examples/`](examples/): the course and the five refusals, each with what went in and what came back |

## How a request travels

```
author ──► membrane ──────────────────────────► machine ──► trace ──► LTL invariants
           registered? schema? policy (OPA)?    transition table from the spec;
           legal in this state? idempotent?     each guard answered by its engine
           under the rate limit?                (Z3 · Datalog · Prolog · JSON Schema)
                │
                ├──► Generator port   (recorded · Gemini)            the model writes
                └──► Screener port    (recorded · Bedrock, not built)  the guardrail reads
```

The membrane runs before anything is paid for: an action that is not registered,
not well-formed, not permitted, or not legal in the current state never reaches
a model. What comes back is an event the machine judges, not an instruction it
follows. The prompt is not a string: the rules, the author's text and the
retrieved sources travel in separate positions, and only a provider adapter may
join them.

## What is here

| | |
|---|---|
| `model/` | vendored from the specification at a tag, with `model.lock` |
| `machine/` | the state machine: built from the transition table, guards answered by the engines, every step written to the trace |
| `engines/` | the six layers that can refuse — `opa/`, `z3/`, `datalog/`, `prolog/`, `schema/`, `temporal/` — behind one contract |
| `gateway/` | the membrane, the eleven-stage pipeline, and what the guardrail is shown |
| `gateway/provider/` | the ports: a generator and a screener; the recorded adapters, a Gemini generator, Bedrock stubs, and the one module that builds an AWS client |
| `scenarios/` | the runs behind the `make` targets above |
| `fixtures/` | an invented organisation; `namespace.yaml` is the only vocabulary allowed |
| `fixtures/evil-twins/` | seven inputs, one per way the architecture must refuse |
| `tests/` | every test, listed with what it expects in [`docs/test-matrix.md`](docs/test-matrix.md) |

## What the evidence is

- [`docs/test-matrix.md`](docs/test-matrix.md) — every test, the layer that owns
  it, what it expects and what happened. It opens with the eight tests the
  specification says must exist, each mapped to the tests that discharge it.
  Two are honest gaps and one is partial, and the matrix says which and why.
- [`examples/`](examples/) — six input/output pairs: the course from brief to
  rollback with its full trace, and the five refusals with exactly what each
  engine was given and the artifact it returned.
- [`docs/risks.md`](docs/risks.md) — the specification's failure modes and
  assumptions, each with what this repository shows about it, and the
  prototype's own open risks.
- `fixtures/evil-twins/` — each fixture names the guard that must refuse it and
  the layer that owns that guard, and a test checks both against
  `model/guards.yaml`. Five of the seven were wrong when first written.
- CI runs the leak scan, the model check against the published tag, every test,
  the five refusals and the course end to end, and fails if the test matrix or
  the examples in the repository are not the ones the runs produce.

## The live provider

Not yet run. The Gemini generator is written and sits behind the same port as
the recording; a test drives it, holding a key, against a stand-in for Google's
API. The Bedrock generator and the Bedrock Guardrails screener are stubs that
refuse to run, so the screening a live run needs does not exist yet. What does
exist is the fence around the account those adapters will use, reached only
through separate targets so a live call cannot happen by accident:

```bash
make whoami                             # which AWS account a live run would use
make aws ARGS="bedrock list-guardrails" # the only sanctioned way to run the CLI
make model-verify-remote                # also re-fetch the tag, to see if it has moved
```

`make live` runs the tests marked `live`; none are written yet. The recorded
run is what this repository's evidence rests on.

## Two guarantees this repository keeps about itself

**It cannot reach the wrong AWS account.** One module builds the client, checks
its own identity on the same session before any call, and refuses if the account
is not the expected one. A test fails the build if a second module ever
constructs a client, and unit tests run behind credentials that resolve nowhere.

**No name that is not ours reaches the fixtures.** `make leak-scan` allows only
vocabulary that is declared — in `fixtures/namespace.yaml`, or read from the
vendored model, since a fixture naming a guard is quoting the specification
rather than inventing. An allowlist rather than a denylist: a denylist catches
the names someone remembered, and a denylist of real tenants, committed to a
public repository, is itself the list it exists to protect. A canary test proves
the scan still fires, and it is re-run after every loosening.

## Licence

MIT.
