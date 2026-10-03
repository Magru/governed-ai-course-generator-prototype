# The course builder, checked by hand

What a person gives the page, and what the page must show back. Run it before
showing `make ui` to anyone, and after any change under `ui/`. Every expected
value below was read off the recorded cassette, so a difference is a finding,
not noise.

Each step: **ID · given · do · expect**. "Toast" is the message at the foot of
the page; "why" is the red line above the tree; "engines" is the *Refused by
the engines* list in the Governance panel.

## How to run it

- Start a server of its own, not the one being shown: `.venv/bin/python ui/server.py 8801`.
  The page keeps one course on the server, so two people on one server reset
  each other's course.
- Static files are read on every request: a change to `app.js` or `app.css`
  shows on reload. A change to a `.py` file needs the server restarted.
- A browser driver must answer the page's dialogs: Start over asks `confirm`,
  Reject asks `prompt`. Left unanswered, both do nothing.
- Start every section from **Start over**, or from a fresh page with the
  session reset, so no section inherits another's course.
- Never press **Live** in sections R0–R6. Live calls Gemini and Bedrock and
  costs money; it has its own section, R7, run once and on purpose.
- Watch the browser console for the whole run. Apart from the deliberate
  server stop in R6, it stays empty.

## R0 · The page opens

| ID | Given | Do | Expect |
|---|---|---|---|
| R0.1 | server just started | open `http://localhost:8801` | title *New course*, status pill *Draft*, line under it `revision 1 · AwaitingBrief · RecordedGenerator · guardrail guard-1`; segment *Recorded* is on |
| R0.2 | same | look at the tree | an empty card *Create this course with AI* with one **Create with AI** button; no course buttons in the header except *Start over* |
| R0.3 | same | look at Governance | engines: *Nothing refused yet.*; pill *LTL: every invariant holds*; Structure 0, Gateway log 0 |

## R1 · A course, from brief to publication (preset *A course that is published*)

| ID | Given | Do | Expect |
|---|---|---|---|
| R1.1 | R0 | **Create with AI** | a drawer opens from the right: four examples, the first chosen; the form filled from it — title, audience, three skills, 20 minutes, 4 nodes; beside it the JSON the system receives |
| R1.2 | drawer open | press **Esc** | the drawer closes |
| R1.3 | drawer reopened | **Create** | banner *Reading the brief…* while it works; then status *Awaiting approval*, state `OutlineReview`; tree: the course row and the outline offered for approval — four nodes `mt-node-201`…`204` (three topics, one exam), each *Proposed* |
| R1.4 | R1.3 | look at engines | one entry: `datalog · invented-skill` — the first outline named a skill the catalog does not have; the gateway asked again, and the second outline is the one on screen |
| R1.5 | R1.3 | **Approve outline** | state `ContentInProgress`; each node *Planned*, with **Generate** |
| R1.6 | R1.5 | **Generate** on the exam, `mt-node-204` | red toast `NodeGenerationRequested is not permitted … the exam tests material nobody has approved: mt-node-201, mt-node-202, mt-node-203`; engines gains `datalog · outstanding-topics`; the exam stays *Planned* |
| R1.7 | R1.5 | **Generate** `mt-node-201` (Bench safety) | node *Awaiting review*, buttons **Review** and **Approve** |
| R1.8 | R1.7 | **Review** | the lesson editor: crumb `… › Bench safety · 20 min`; the AI-draft bar with **Reject** and **Approve**; eight blocks — the opening line, an image shown as `image · bench.png` with its caption, a heading, three paragraphs each citing its own chunk (`mt-kb-012`, `-013`, `-014`), a checklist and a callout |
| R1.9 | R1.8 | **Approve** in the editor | the editor closes, node *Approved* |
| R1.10 | R1.9 | **Generate** `mt-node-202` (Tool inspection) | node *Awaiting review* with a *1 repair* pill; engines gains `datalog · leak-path` — the first draft cited an article apprentices may not read |
| R1.11 | R1.10 | **Generate** `mt-node-203` (Dust extraction) | node *Awaiting review* with *1 repair*; engines unchanged — the first call timed out and was asked again, which is not a refusal |
| R1.12 | R1.11 | **Approve** 202 and 203, then **Generate** the exam | the exam is generated, *1 repair*, engines gains `schema · failing-path` |
| R1.13 | R1.12 | **Approve** the exam | state `ReadyForReview`; header shows **Send to review** |
| R1.14 | R1.13 | **Send to review** | state `PendingApproval`, status *Awaiting approval*, header shows **Sign approval** |
| R1.15 | R1.14 | **Sign approval** | state `Approved`, header shows **Publish** |
| R1.16 | R1.15 | **Publish** | status *Published* (green), no course button but *Start over*; nodes show only **View**; LTL pill still *every invariant holds* |
| R1.17 | R1.16 | open **Gateway log**, then **Brief** | Gateway log: every stage numbered, its count in the tab; Brief: the JSON that was submitted |
| R1.18 | R1.16 | reload the page | the same course, in the same state |

## R1b · The brief, as a person fills it

Each field is labelled with who reads it. Only the title and the skills reach
the model; the rest is judged before it is asked. In Recorded mode the title
is the example's and cannot be edited — the recorded guardrail answered for
that text only; everything else can be changed and is judged by the real
engines. Only the published course has a recorded model behind it, and its
outline is fixed: changing its skills or count changes what the checks judge,
not what the model proposes; a count other than 4 is not held against the
outline (see `risks.md`). A refusal example fixed in Recorded stops at
*nothing recorded*, and the why line says Live carries it on.

| ID | Given | Do | Expect |
|---|---|---|---|
| R1b.1 | drawer open, Recorded | look at the title | read-only, with the note why |
| R1b.2 | same | press the *Noise exposure* skill | it turns blue; `"noise-exposure"` is added to `objectives` in the JSON, and that field lights up |
| R1b.3 | same | type `40` in *Minutes per lesson*, **Create** | `BlockedRecoverable`; why: `z3 — these requirements cannot hold together: max_minutes_per_lesson, minutes_per_lesson` |
| R1b.4 | Start over, drawer open | empty *Nodes in the course*, **Create** | `requested_nodes` gone from the JSON; why: `z3 — this brief cannot be judged: how many nodes the course should have` — Z3 never guesses a number the author left out |
| R1b.5 | Start over, drawer open | swap *Apprentices* for *Supervisors*, **Create** | `BlockedFinal`; why: `opa — audience_permitted: author-1 may not author for ["supervisors"]` |
| R1b.6 | drawer open | press the example *A brief that cannot hold* | the form refills: twelve skills, 40 minutes, 14 nodes |
| R1b.7 | any | change a field, then look at the JSON | `id` is the system's and never changes; an empty field leaves its key out |

## R1c · The outline, reviewed by a person

The outline is a proposal: nothing is written yet, so its nodes open nothing.
A person may approve it, remove what does not belong, or reject it with a
reason — the three events the specification gives this state.

| ID | Given | Do | Expect |
|---|---|---|---|
| R1c.1 | R1.3 | look at the header and the tree | **Reject outline** beside **Approve outline**; each node *Proposed*, with **Remove**; above the tree: *nothing is written yet* |
| R1c.2 | R1c.1 | **Reject outline**, reason `only the skills in the brief` | an outline again, in `OutlineReview`; the trace has `OutlineRejected`. Live: the model is sent that reason and drafts a new one. Recorded: the recording answers with the same outline |
| R1c.3 | R1c.1 | **Remove** on *Tool inspection*, Cancel | a warning that the brief asks for this skill; nothing changes |
| R1c.4 | R1c.3 | **Remove** again, OK | three nodes; the exam is now over `mt-node-201, mt-node-203`; the trace has `OutlineRevised`, and the edited outline went through the outline's checks |
| R1c.5 | R1c.4 | approve, generate and approve each node, **Send to review** | sent back: `tool-inspection is not covered: no node in this course teaches it`; LTL still holds |
| R1c.6 | a brief without *Dust extraction*, Recorded | Create | *Dust extraction* is tagged **not in the brief**: the catalog allows it, the brief did not ask for it, and the person decides |

## R2 · Three briefs the system must refuse

| ID | Given | Do | Expect |
|---|---|---|---|
| R2.1 | Start over | Create with *A forbidden topic* | state `BlockedFinal`, status *Blocked*; why names the guardrail stage and `deny: defeating-a-guard`; engines says no engine refused, because the guardrail, not an engine, stopped it; no **Release** — a final block is final |
| R2.2 | Start over | Create with *A brief that cannot hold* | state `BlockedRecoverable`, blocked at the brief; engines: `z3 · unsat-core` naming the requirements that cannot hold together; **no Release button**, because releasing cannot fix a brief; the empty tree says to start over with a different brief |
| R2.3 | Start over | Create with *An audience not granted* | state `BlockedFinal`; engines: `opa · named-rule · audience_permitted: author-1 may not author for ["supervisors"]`; the gateway stopped at the policy stage, before any model was asked |

## R3 · A lesson rejected

A lesson may be repaired twice before it waits for a person: that is the
machine's repair budget, not a limit of the page.

| ID | Given | Do | Expect |
|---|---|---|---|
| R3.1 | course preset, outline approved, `mt-node-201` generated | Review → **Reject**, reason `too short` | node *Drafting*, a line `refused: too short`, a *1 repair* pill |
| R3.2 | R3.1 | **Generate** `mt-node-201` | *Awaiting review*; in the editor the first block ends `(revised after review 1)` |
| R3.3 | R3.2 | Reject again, Generate | *Awaiting review*, *2 repairs*, the first block ends `… 2)` |
| R3.4 | R3.3 | Reject a third time | node *Needs a person*; course *Blocked*; why reads `Bench safety — <the reason>`, not an older refusal; **Release — fixed by a person** in the header |
| R3.5 | R3.4 | **Release** | course back in `ContentInProgress`, node *Drafting* with **Generate** |
| R3.6 | R3.5 | **Generate**, then **Approve** | the first block ends `… 3)`; node *Approved*; LTL holds |

Three revised drafts are recorded per lesson. A fourth rejection followed by
Generate runs out of recordings: the lesson goes to *Recovering* and why reads
`effect: nothing recorded …` — the cassette's limit, said as what it is.

## R4 · Moving between screens

| ID | Given | Do | Expect |
|---|---|---|---|
| R4.1 | a course on screen | **Start over**, answer *Cancel* | nothing changes |
| R4.2 | same | **Start over**, answer *OK* | back to R0.1 |
| R4.3 | the server started without `BEDROCK_GUARDRAIL_ID` or `_VERSION` (`make ui` exports them from `.env`; start it directly to check this) | press **Live**, confirm | red toast `live mode needs BEDROCK_GUARDRAIL_ID and BEDROCK_GUARDRAIL_VERSION …`; the segment stays on *Recorded*; the course on screen is kept |
| R4.4 | R4.3 | press **Recorded** (already on) | nothing happens |

## R5 · Screens it may be shown on

At each size, on R1.5 (course with Generate buttons) and R1.8 (editor open):
no horizontal scroll; header buttons do not overlap the title; every node row
shows its title, its pills and its buttons; the editor and the drawer fit.

| ID | Screen |
|---|---|
| R5.1 | 1920×1080 |
| R5.2 | 1366×768 |
| R5.3 | 1280×720 |
| R5.4 | 1920×1080 at 150% zoom (a 1280×720 page) |

## R6 · When the server goes away

| ID | Given | Do | Expect |
|---|---|---|---|
| R6.1 | a course on screen | stop the server, press any button | a red toast that the page lost the server; the banner goes away; buttons are usable again; the console holds only the browser's own `ERR_CONNECTION_REFUSED` lines, no script error |
| R6.2 | R6.1 | restart the server, reload | a fresh course, R0.1 |

## R7 · Live, once

Needs `GEMINI_API_KEY` and `BEDROCK_GUARDRAIL_ID` / `_VERSION` in `.env`, and
costs a few cents. The model's answers differ run to run, so only what must
hold is checked, not what it writes.

| ID | Given | Do | Expect |
|---|---|---|---|
| R7.1 | Start over | press **Live** | segment *Live · Gemini + Bedrock*; line under the title names `GeminiGenerator` and the guardrail version |
| R7.2 | R7.1 | Create the published-course brief | an outline in `OutlineReview` within a minute, or a refusal that names its engine or the guardrail |
| R7.3 | R7.2 | Approve outline, Generate and Approve each node, Send to review, Sign, Publish | either *Published*, or a stop whose why names a stage or engine; a lesson that stops at *Recovering* can be released by a person; an outline the checks refused shows its nodes as *Refused* and offers only Start over |
| R7.4 | any | throughout | LTL pill holds; no console error; the banner never stays after a call returns |

## Last run

| Date | Server | R0 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | Fixed on the way |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-02 | `ui/server.py 8801`, recorded; system Chrome 154 driven by Playwright 1.60 | pass | pass | pass | pass | pass | pass | pass | not run | the outline is shown before it is approved; Esc closes the drawer; Release only where a person can act on it, and a brief or outline that cannot hold says to start over; a refused outline is shown as refused; a stop names its own cause, not an earlier refusal; a lesson can be rejected until the repair budget hands it to a person; a stale red toast is cleared by the next button; a lost server no longer throws in the console; the lessons keep their room at 1280; Live needs both the guardrail and its version |
| 2026-10-02 | `make ui` on 8800, Live: Gemini 2.5 Flash + guardrail `mt-guard` v1 | — | — | — | — | — | — | — | first: sent back at the course checks; second: pass, Published in 49 s of calls | the model is told what an exam's topics are; the page says why the course checks sent a course back |
| 2026-10-03 | `ui/server.py 8801`, recorded; Chrome 154 via Playwright 1.60 | pass | pass (+R1b) | pass | pass | pass | pass | pass | — | the brief is a form a person fills in, with the JSON beside it; the title stays the example's in Recorded mode, on the page and on the server |
| 2026-10-03 | `ui/server.py 8801`, recorded; Chrome 154 via Playwright 1.60 | pass | pass (+R1b, R1c) | pass | pass | pass | pass | pass | — | the outline can be rejected with a reason and edited node by node; a removed node leaves the exam too; a skill the brief did not ask for is tagged |
| 2026-10-03 | `make ui UI_PORT=8802`, branch with lessons scoped and counted; Live | pass | pass | pass | pass | pass | pass | pass | first: not published (lessons stated exam fields; off-brief lessons approved unreviewed; a guardrail denial); second: Published in 106 s, lessons 320–430 words | lessons are scoped to their skill, asked for by length and counted against their minutes; a lesson is not offered an exam's fields |
| 2026-10-03 | branch final: recorded on 8801, Live on 8802 | pass | pass | pass | pass | pass | pass | pass | Published, lessons 366–418 words; one guardrail denial repaired | the word floor holds to the brief's minutes; an exam over no node keeps its sources |
