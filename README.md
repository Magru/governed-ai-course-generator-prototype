# Governed AI Course Generator — prototype

The runnable half of a specification published at
**[magru.github.io/governed-ai-course-generator](https://magru.github.io/governed-ai-course-generator/)**.

The specification is not documentation about this code. It is this code's input:
the state machine is loaded from `model/transitions.yaml`, the properties it must
satisfy from `model/invariants.yaml`, and `make model-verify` fails the build if
the vendored copy has drifted from the published tag.

## Run it

```
make setup
make test
```

No AWS account, no API key, no network. Everything runs against an invented
organisation under `fixtures/`.

A live run against a model provider is opt-in and needs credentials:

```
make whoami          # which account a live run would use
LIVE=1 make test
```

## What is here

| | |
|---|---|
| `model/` | vendored from the specification at a tag, with `model.lock` |
| `engines/` | OPA, Z3, Datalog, Prolog and a finite-trace temporal checker |
| `machine/` | the loader that turns the transition table into a running machine |
| `gateway/` | the eleven stages every generated artifact passes through |
| `fixtures/` | an invented organisation; `namespace.yaml` is the only vocabulary allowed |
| `tests/` | including the tests that keep the other guarantees honest |

## Two guarantees this repository keeps about itself

**It cannot reach the wrong AWS account.** One module builds the client, checks
its own identity on the same session before any call, and refuses if the account
is not the expected one. A test fails the build if a second module ever
constructs a client, and unit tests run behind credentials that resolve nowhere.

**No name that is not ours reaches the fixtures.** `make leak-scan` allows only
the vocabulary declared in `fixtures/namespace.yaml` — an allowlist rather than a
denylist, because a denylist catches the names someone remembered and this
catches the ones they did not. A canary test proves the scan still fires.

## Licence

MIT.
