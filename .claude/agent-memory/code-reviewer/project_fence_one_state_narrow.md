---
name: project-fence-one-state-narrow
description: Recurring audit pattern in the Sylla prototype - spec fixes fence one state narrower than the threat; check landing guards and all node states
metadata:
  type: project
---

Across audit passes 3-5 (Sept 2026) the same shape kept coming back: a spec fix guards the entry to a state (or a subset of source states) while the threat also arrives through a neighbouring path. Examples: exam I2 fenced at NodeRepair exit, then at ContentDrafting/NodeRecovery, but still open through an outline commit that widens topics(node) and through exams already in OutputGuardrail/Validated; guardrail version stamped correctly at screening but overwritten by store versions at NodeApproved.

**Why:** the spec is edited row by row from the previous finding, so each fix covers exactly the reported scenario.

**How to apply:** for any fence/guard change, enumerate every row entering the protected state and every event that changes the guard's inputs (not only edits: outline commits, version broadcasts, approvals). Prefer recommending the guard on the landing event itself. Probes live in the session scratchpad (audit5/, audit6/); `permits()` loop over all events is a cheap deadlock check.

Pass 6 (spec-v2.12) repeated it on the event axis: a fence keyed to an *event* (config broadcast row) is bypassed by paths that copy state instead of transitioning — `fork()` and StaleReview `_restamp` carry stale stamps into a draft with no event. Also check the *revision state* a node row runs under: node rows without `course_state` let NodeChecks run outside ContentInProgress, where OPA `state_permits` turns into terminal BlockedFinal. A random-walk harness (audit7/walk.py) with per-step predicates (publish-time stamps, BlockedFinal in draft, terminal nodes moving) found both; `permits()`-empty "stuck" checks are masked by no-op BlockedInputFixed loops.
