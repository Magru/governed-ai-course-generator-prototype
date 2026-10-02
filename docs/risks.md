# Risks

Three lists, each with what the prototype shows about it. The first is the
specification's failure modes, from `safety.html` §10. The second is its
assumptions, from `model/assumptions.yaml`. The third is the risks of this
prototype itself, which the specification could not have known about.

The column that matters is the last one in each table. A risk the
specification answers and this repository does not demonstrate is still a
risk. The table says which those are.

## 1 · Failure modes: what stops each one, and where it is shown

| failure mode | what stops it | owner | shown here by |
|---|---|---|---|
| Wrong action | the transition table; publication has an event of its own | State machine | `test_machine_conformance.py`, `test_machine_runs.py`; [`examples/01`](../examples/01-a-course-published-and-rolled-back/) |
| Bad arguments | schema validation; extra fields rejected, now including a node's own fields | JSON Schema | `test_engine_schema.py`, `test_gateway_membrane.py::test_an_extra_field_is_refused_not_ignored`, `test_injection_surfaces.py` |
| Unauthorized resource | resource-level authorization, not just role | OPA | `test_engine_opa.py`; [`examples/03`](../examples/03-an-audience-the-author-was-not-granted/) |
| Over-agency | actions are per node and per request; nothing batches on its own | Registry | `test_gateway_membrane.py::test_the_registry_is_the_eleven_actions_the_specification_lists` |
| Duplicate side effect | idempotency key issued before the call, marked landed after | State store | `test_gateway_idempotency.py`, `test_gateway_membrane.py::test_issued_and_landed_are_two_facts` |
| Output injection | untrusted position, screening on the way out | Guardrail | `test_injection_surfaces.py`, `test_prompt_positions.py`. **The admission screen and the recorded attempt are not built**: see §3 |
| Secret leakage | secret detection before context admission | Scanner | **No scanner is built.** `test_injection_surfaces.py` shows no credential reaches a prompt, which is prevention by construction, not detection |
| Unsafe retry | check by key first; retry is bounded | State machine | `test_end_to_end.py::test_a_timeout_is_retried_under_the_same_key_and_lands_once`, `test_gateway_membrane.py::test_a_call_that_never_answered_is_retried_under_the_same_key` |
| Bad context admission | admission control and summarization | Guardrail | rights filter on retrieval (`gateway/retrieval.py`); **no summarization step** |
| No audit | one trace per course, every action in it | Temporal logic | `test_engine_temporal.py`; `trace.json` in [`examples/01`](../examples/01-a-course-published-and-rolled-back/) |
| Infeasible request | satisfiability before the first token, with the conflict named | Z3 | `test_engine_z3.py`; [`examples/02`](../examples/02-a-brief-that-cannot-be-satisfied/) |
| Ungrounded claim | grounding over the citation graph | Datalog | `test_engine_datalog.py`, `test_datalog_structure.py` |
| Permission leak | the leak path, derived rather than asserted | Datalog | `test_engine_datalog.py`; [`examples/04`](../examples/04-a-node-citing-a-source-its-audience-cannot-see/) |
| Unmet objective | coverage, refused with a proof tree | Prolog | `test_engine_prolog.py`; [`examples/05`](../examples/05-an-objective-nothing-approved-covers/) |

A published course with a stale node is not a row of its own in §10, but it is
the property most of the machine exists to keep:
[`examples/06`](../examples/06-a-course-published-with-a-stale-node/).

## 2 · Assumptions: what the design relies on, and whether anything here checks it

`model/assumptions.yaml` lists eleven. None is monitored, which is true of the
specification and of this prototype alike: there is no production to monitor.
The question here is narrower. When an assumption fails, does the prototype
behave the way the specification says it should?

| | assumption | if it is false | the prototype |
|---|---|---|---|
| A1 | the stamped catalog version is the one still served | a node passes against a catalog that no longer exists | **reacts**: a catalog change sends checked draft nodes back through the checks and to a person (`test_draft_follows_the_rules_in_force.py::test_a_catalog_change_sends_checked_nodes_back_through_the_checks_and_to_a_person`). Nothing *detects* the drift; the change is an event someone must send |
| A2 | the policy bundle in force is the one the revision was verified against | a course is live under a rule never applied to it | **reacts**: `test_machine_after_publication.py::test_a_rule_change_re_verifies_what_it_reaches_and_leaves_the_rest_alone` |
| A3 | the Datalog fact mirror is fresh | a revoked permission passes a check on stale truth | **not shown**: the organisation is a fixture and there is no mirror to fall behind |
| A4 | the guardrail is reachable, and its verdict is authoritative | work stops, or a missing verdict is read as permission | **reacts**: an unreachable or malformed answer is never a verdict and spends the retry budget (`test_gateway_answers_it_can_vouch_for.py`, `test_machine_after_publication.py::test_an_unreachable_guardrail_spends_the_budget_and_the_emergency_lever_still_works`) |
| A5 | the model honours the forced output schema | the repair loop absorbs failures and cost rises unseen | **reacts**: a malformed answer is repaired with the path it got wrong (`test_end_to_end.py::test_the_repair_prompt_carries_the_refusal_not_just_a_retry`). The failure rate is not measured |
| A6 | the repair loop converges inside its budget | editors receive blocked nodes instead of drafts | **bounded, not measured**: the budget ends every loop (`test_machine_runs.py`); `make cascade` prices the worst case |
| A7 | an idempotency key is unique to one canonical action | a retry performs the effect twice | **shown**: `test_gateway_idempotency.py`; a key is the canonical form of the action, so `40` and `40.0` are one act |
| A8 | the editor reads what they approve | every guard passes and governance stops, invisibly | **cannot be shown by code**: the specification says so, and so does this |
| A9 | over-refusal is rare | authors quietly stop using the generator | **not shown**: the recording has no over-refusal in it |
| A10 | clocks agree well enough to order by `event_time` | a trace replays in an order that never happened | **not exercised**: `event_time` here is a step counter, so there is no clock to disagree |
| A11 | the stamped guardrail version is the one the service enforces | a course serves under a replaced rule | **reacts**: an answer from the version being replaced is no answer (`test_machine_after_publication.py::test_a_verdict_from_the_version_being_replaced_is_no_answer`) |

## 3 · The prototype's own risks

| risk | what it means | state |
|---|---|---|
| The evidence rests on a recording | every model and guardrail answer in the tests comes from `scenarios/cassette.py` | by design: the run is repeatable and needs no account. The live guardrail gave the recording's answers on every known case (`make live`) |
| The live run reached one node | three runs of `make live-run` ([`live-run.md`](live-run.md)): the third wrote, screened and checked the first topic; no live run has yet reached publication. Images cannot be screened live: the prototype has no image provider, so a node naming an image is never admitted | open: a full live course needs a person to approve each node |
| A source's injection attempt is not recorded | none of the five screening points reads a retrieved source | open; inert by position, so the attempt fails, but nothing knows it was tried (`fixtures/evil-twins/07`) |
| No PII redaction | the invented organisation's sources hold no personal data | open; the step does not exist |
| A guardrail rollout spends the retry budget | while the service still answers as the version being replaced, each answer is no answer | accepted: the budget ends it and a person releases the course once the rollout lands |
| Each edit to a topic during exam generation costs one paid call | the exam goes back to wait, and the call already made does not land | accepted: the waiting costs no retry, and `make cascade` shows the cascade settles |
| Ten modules are longer than 200 lines | the longest: `engines/temporal/invariants.py`, `machine/machine.py`, `gateway/pipeline.py`, `machine/bookkeeping.py`, `machine/store_guards.py` | deferred: splitting them before the defence risks more than it buys |
