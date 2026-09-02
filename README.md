# Governed AI Course Generator — prototype

The runnable half of a specification published at
**[magru.github.io/governed-ai-course-generator](https://magru.github.io/governed-ai-course-generator/)**.

The specification is not documentation about this code. It is this code's input:
the state machine is loaded from `model/transitions.yaml`, the properties it must
satisfy from `model/invariants.yaml`, and `make model-verify` fails the build if
the vendored copy has drifted from the published tag.

## Run it

```
make setup           # this one installs dependencies, so it does need the network
make test
```

`make test` needs no AWS account, no API key and no network: unit tests run
behind credentials that resolve nowhere, and the model check compares against
the lock rather than re-fetching it. Everything runs against an invented
organisation under `fixtures/`.

The parts that do reach outward are separate targets, so they cannot be reached
by accident:

```
make whoami              # which AWS account a live run would use
make live                # the few tests that need the real provider
make model-verify-remote # also re-fetch the tag, to see if it has moved
make aws ARGS="bedrock list-guardrails"   # the only sanctioned way to run the CLI
```

## What is here

| | |
|---|---|
| `model/` | vendored from the specification at a tag, with `model.lock` |
| `gateway/provider/` | the ports: a generator, a screener, and the one module that builds an AWS client |
| `fixtures/evil-twins/` | seven inputs, one per way the architecture must refuse |
| `engines/`, `machine/`, `gateway/` | empty; phases 02 and 03 |
| `fixtures/` | an invented organisation; `namespace.yaml` is the only vocabulary allowed |
| `tests/` | including the tests that keep the other guarantees honest |

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

**And what the fixtures claim about the specification is checked against it.**
Each refusal fixture names the guard that must refuse it and the layer that owns
that guard; a test compares both with `model/guards.yaml`. Five of the seven were
wrong when first written, and no amount of reading had caught it.

## Licence

MIT.
