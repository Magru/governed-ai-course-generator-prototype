// The page reads the whole state after every button and draws it. Nothing here
// decides what is allowed: a button appears for the state the machine reports,
// and one the machine refuses shows the machine's reason.
(() => {
  const MAIN = ["AwaitingBrief", "BriefValidation", "BriefFeasibility", "OutlineDrafting", "OutlineGuardrail",
    "OutlineChecks", "OutlineReview", "ContentInProgress", "ReadyForReview", "WholeCourseChecks",
    "PendingApproval", "Approved", "Published"];
  const OFF = ["OutlineRepair", "ErrorRecovery", "BlockedRecoverable", "BlockedFinal", "StaleReview",
    "Withdrawn", "Superseded"];
  const BAD = new Set(["OutlineRepair", "ErrorRecovery", "BlockedRecoverable", "BlockedFinal", "StaleReview", "Withdrawn"]);
  const PERSON = new Set(["OutlineReview", "PendingApproval"]);
  const COURSE_ACTS = { "approve-outline": "OutlineReview", "checks": "ReadyForReview", "sign": "PendingApproval",
    "publish": "Approved", "release": "BlockedRecoverable" };
  const NODE_PILL = {
    Proposed: ["review", "Proposed"], Refused: ["bad", "Refused"], Planned: ["", "Planned"], ContentDrafting: ["work", "Drafting"], Generated: ["work", "Drafting"],
    OutputGuardrail: ["work", "Screening"], NodeChecks: ["work", "Checking"], Validated: ["review", "Awaiting review"],
    NodeApproved: ["ok", "Approved"], NeedsRevalidation: ["work", "Re-checking"], NodeRepair: ["bad", "Needs a person"],
    NodeRecovery: ["bad", "Recovering"], BlockedFinal: ["bad", "Blocked"], Removed: ["", "Removed"],
  };

  const $ = s => document.querySelector(s);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const icon = (id, cls = "ico") => { const ns = "http://www.w3.org/2000/svg"; const s = document.createElementNS(ns, "svg"); s.setAttribute("class", cls); const u = document.createElementNS(ns, "use"); u.setAttribute("href", `#i-${id}`); s.append(u); return s; };
  const words = s => (s || "").replace(/[-_]/g, " ").replace(/^./, c => c.toUpperCase());
  let state = null, presets = {}, form = null, chosen = "course", seenStages = 0, shown = {};

  async function api(path, body) {
    const r = await fetch(`/api/${path}`, body === undefined ? {} :
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok && body === undefined) throw new Error(`${path}: ${r.status}`);   // a read the server does not know
    return r.json();
  }

  function toast(text, bad) {
    const t = $("#toast"); t.textContent = text; t.className = `toast show${bad ? " bad" : ""}`;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { t.className = "toast"; }, bad ? 7000 : 2600);
  }

  function working(on, title) {
    $("#banner").hidden = !on;
    if (title) $("#banner-title").textContent = title;
    $("#banner-sub").textContent = state?.mode === "live"
      ? "asking Gemini, then Bedrock Guardrails, then the checks — a few seconds per call"
      : "the recorded model and guardrail answer; the machine and the engines are real";
    document.querySelectorAll("button").forEach(b => { if (on) b.dataset.was = b.disabled ? "1" : ""; b.disabled = on || b.dataset.was === "1"; });
  }

  function quiet() { clearTimeout(toast.timer); $("#toast").className = "toast"; }

  async function act(name, body = {}, title = "Working…") {
    working(true, title); quiet();
    try {
      const out = await api(name, body);
      if (!out.ok) toast(out.error, true);
    } catch { /* the server is gone: refresh() below says so */ } finally { working(false); document.querySelectorAll("button").forEach(b => { b.dataset.was = ""; }); await refresh(); }
  }

  // ── the header, the lifecycle, the tabs ─────────────────────────────
  function drawHead(s) {
    const st = s.revision.state;
    $("#course-title").textContent = st === "AwaitingBrief" ? "New course" : s.brief.title;
    const status = $("#status");
    const [cls, label] = st === "Published" ? ["published", "Published"] : BAD.has(st) ? ["blocked", "Blocked"]
      : PERSON.has(st) || st === "Approved" ? ["review", st === "Approved" ? "Approved" : "Awaiting approval"] : ["draft", "Draft"];
    status.className = `status ${cls}`; status.textContent = label;
    $("#save").textContent = `revision ${s.revision.id} · ${st} · ${s.generator} · guardrail ${s.guardrail}`;
    $("#side-guard").textContent = `v${s.guardrail}`.replace("vguard-", "v");
    Object.entries(COURSE_ACTS).forEach(([name, at]) => { $(`[data-act="${name}"]`).hidden = st !== at; });
    $("#reject-outline").hidden = st !== "OutlineReview";
    // A person can release what blocked a lesson. A brief or an outline that
    // cannot hold is not released but drafted again from a new brief, and the
    // page has no button that would draft it, so there is nothing to press.
    if (["brief", "outline"].includes(s.revision.blocked_at)) $('[data-act="release"]').hidden = true;
    document.querySelectorAll("[data-mode]").forEach(b => b.classList.toggle("on", b.dataset.mode === s.mode));
    $("#count-nodes").textContent = s.nodes.length;
    $("#count-stages").textContent = s.stages.length;
  }

  function drawLifecycle(s) {
    const box = $("#lifecycle"); box.replaceChildren();
    const here = s.revision.state, at = MAIN.indexOf(here);
    const chip = (n, i) => {
      const c = el("span", "st", n);
      if (n === here) c.classList.add("here", BAD.has(n) ? "bad" : PERSON.has(n) ? "person" : n === "Published" ? "ok" : "x");
      else if (at >= 0 && i < at) c.classList.add("passed");
      return c;
    };
    MAIN.forEach((n, i) => { if (i) box.append(el("span", "sep", "›")); box.append(chip(n, i)); });
    box.append(el("span", "gap"));
    OFF.forEach(n => box.append(chip(n, -1)));
  }

  // ── the structure ───────────────────────────────────────────────────
  function drawTree(s) {
    const tree = $("#tree"); tree.replaceChildren();
    const st = s.revision.state;
    const why = $("#why");
    // Who stopped it, in the order a reader looks: what the last button hit —
    // a screening that denied, a call that failed — then a lesson waiting for a
    // person, then an engine's refusal with its artifact, then whatever reason
    // the machine kept. An earlier step's refusal, already settled, is not it.
    const stuck = s.nodes.find(n => ["NodeRepair", "NodeRecovery", "BlockedFinal"].includes(n.state));
    const heard = s.last_act.engines[s.last_act.engines.length - 1];
    const refused = !BAD.has(st) ? null
      : recordedOut(lastStage(s.last_act.stages, /^(deny|unreachable|effect)/))
      || (stuck && `${stuck.type === "exam" ? "Exam" : words(stuck.skill)} — ${stuck.last_refusal || NODE_PILL[stuck.state][1].toLowerCase()}`)
      || (heard && `${heard.engine} — ${heard.summary}`) || s.revision.last_refusal || "see the Gateway log";
    // The course checks can also send a course back rather than block it: the
    // machine moves on, so nothing else on the page would say why.
    const sentBack = !refused && s.events[s.events.length - 1]?.event === "CheckFailed" && s.revision.last_refusal;
    why.hidden = !(refused || sentBack);
    why.textContent = refused ? `Stopped at ${st} · ${refused}` : sentBack ? `Sent back by the course checks · ${sentBack}` : "";

    if (!s.nodes.length) {
      const empty = el("div", "empty");
      const tile = el("div", "tile"); tile.append(icon("sparkles"));
      const hint = st === "AwaitingBrief" ? "Describe the course; the model drafts an outline, and nothing reaches a learner until a person approves it."
        : st === "BlockedFinal" ? "This brief is refused for good. Start over with a different one."
        : s.revision.blocked_at === "brief" ? "The brief cannot hold as written. Start over with a different one."
        : "The brief did not get as far as an outline.";
      empty.append(tile, el("b", "", st === "AwaitingBrief" ? "Create this course with AI" : "No outline yet"), el("span", "muted", hint));
      if (st === "AwaitingBrief") {
        const b = el("button", "btn primary"); b.type = "button"; b.append(icon("sparkles"), document.createTextNode("Create with AI"));
        b.onclick = openDrawer; empty.append(b);
      }
      tree.append(empty); return;
    }
    const section = el("div", "row");
    const tile = el("div", "tile t-section"); tile.append(icon("layers"));
    const main = el("div", "row-main");
    main.append(el("div", "row-title", s.brief.title), el("div", "row-sub", `${s.nodes.length} nodes · audience ${(s.brief.audience || []).join(", ")}`));
    section.append(icon("grip", "grip"), tile, main);
    tree.append(section);

    const working = st === "ContentInProgress", reviewing = st === "OutlineReview";
    $("#tree-sub").textContent = reviewing
      ? "Proposed: nothing is written yet. Approve the outline, remove what does not belong, or reject it with a reason."
      : "The model proposes. A person approves.";
    const asked = new Set(s.brief.objectives || []);
    s.nodes.forEach(n => {
      const row = el("div", "row child");
      const t = el("div", `tile ${n.type === "exam" ? "t-exam" : "t-topic"}`); t.append(icon(n.type === "exam" ? "quiz" : "file"));
      const m = el("div", "row-main");
      const title = el("div", "row-title", n.type === "exam" ? "Exam" : words(n.skill));
      const [pc, pl] = NODE_PILL[n.state] || ["", n.state];
      title.append(el("span", `pill ${pc}`, pl));
      if (n.repairs) title.append(el("span", "pill bad", `${n.repairs} repair${n.repairs > 1 ? "s" : ""}`));
      // Shown, not decided: the catalog allows the skill, the brief did not ask
      // for it, and whether it belongs is the person's call.
      if (n.state === "Proposed" && n.skill && !asked.has(n.skill)) title.append(el("span", "pill warn", "not in the brief"));
      m.append(title, el("div", "row-sub", n.type === "exam" ? `${n.id} · over ${(n.topics || []).join(", ")}` : n.id));
      if (n.last_refusal && !["NodeApproved", "Validated"].includes(n.state)) m.append(el("div", "row-why", `refused: ${n.last_refusal}`));
      const actions = el("div", "row-actions");
      const btn = (cls, ic, label, on) => { const b = el("button", `btn sm ${cls}`); b.type = "button"; b.append(icon(ic), document.createTextNode(label)); b.onclick = on; actions.append(b); };
      if (working && ["Planned", "ContentDrafting", "OutputGuardrail"].includes(n.state))
        btn("primary", "sparkles", "Generate", () => act("generate", { node: n.id }, `Writing ${n.type === "exam" ? "the exam" : words(n.skill)}…`));
      if (n.content) btn("ghost", "eye", n.state === "Validated" ? "Review" : "View", () => openEditor(n));
      if (working && n.state === "Validated") btn("outline", "check", "Approve", () => act("approve", { node: n.id }, "Recording the approval…"));
      if (reviewing) btn("ghost", "x", "Remove", () => {
        const name = n.type === "exam" ? "The exam" : words(n.skill);
        if (n.skill && asked.has(n.skill) && !confirm(`${name} is one of the skills the brief asks for. The outline's checks will accept the edit, but the course checks will refuse a course that does not teach it. Remove it anyway?`)) return;
        act("remove-node", { node: n.id }, "Checking the edited outline…");
      });
      row.append(icon("grip", "grip"), t, m, actions);
      tree.append(row);
    });
  }

  // The cassette has answers for the examples as they are; a brief changed
  // past them reaches a question nobody recorded, and the page says so.
  const recordedOut = why => why && /nothing recorded/.test(why)
    ? `${why} — Recorded mode has no model answer for this brief; switch to Live to carry it on` : why;

  function lastStage(stages, re) { const hit = [...stages].reverse().find(x => re.test(String(x[3]))); return hit ? `${hit[1]} — ${hit[3]}` : ""; }

  // ── governance ──────────────────────────────────────────────────────
  function stageItem([n, name, subject, result], fresh) {
    const text = String(result);
    const cls = text.startsWith("allow") ? "allow" : /^(deny|effect|unreachable|answer)/.test(text) ? "deny" : text.includes("repaired") ? "repaired" : "";
    const li = el("li", `${cls}${fresh ? " fresh" : ""}`);
    li.append(el("span", "n", n), el("span", "name", name), el("span", "subject", subject), el("span", "result", text));
    return li;
  }

  function drawGovernance(s) {
    const eng = $("#engines"); eng.replaceChildren();
    if (!s.engine_log.length) eng.append(el("li", "muted", BAD.has(s.revision.state)
      ? "No engine refused this course; what stopped it is named above the structure." : "Nothing refused yet."));
    [...s.engine_log].reverse().forEach(e => { const li = el("li"); li.append(el("span", "eng", e.engine), el("span", "kind", e.kind), document.createTextNode(e.summary)); eng.append(li); });
    const recent = $("#recent"); recent.replaceChildren();
    s.stages.slice(-9).forEach((x, i, all) => recent.append(stageItem(x, s.stages.length - all.length + i >= seenStages)));
    const all = $("#stages"); all.replaceChildren();
    s.stages.forEach((x, i) => all.append(stageItem(x, i >= seenStages)));
    seenStages = s.stages.length;
    const ev = $("#events"); ev.replaceChildren();
    s.events.forEach(e => ev.append(el("span", e.event === "(auto)" ? "auto" : "", e.event)));
    ev.scrollTop = ev.scrollHeight;
    const ltl = $("#ltl"); const ok = s.ltl === "every invariant holds";
    ltl.className = `pill ${ok ? "ok" : "bad"}`; ltl.textContent = ok ? "LTL: every invariant holds" : `LTL: ${s.ltl}`;
    $("#provider").textContent = `${s.generator} · guardrail ${s.guardrail}`;
    $("#brief").textContent = JSON.stringify(s.brief, null, 2);
  }

  function draw(s) { state = s; drawHead(s); drawLifecycle(s); drawTree(s); drawGovernance(s); }
  async function refresh() {
    try { draw(await api("state")); }
    catch (e) { toast(`The page lost the server: ${e.message}. Is make ui still running?`, true); }
  }

  // ── create with AI ──────────────────────────────────────────────────
  // The author fills a form; the page turns each choice into the brief's
  // fields and shows the JSON as it changes. The id is the system's, not the
  // author's, and nothing here checks a value: the engines do, after Create.
  function drawPresets() {
    const box = $("#presets"); box.replaceChildren();
    Object.entries(presets).forEach(([k, v]) => {
      const b = el("button", `example${k === chosen ? " on" : ""}`, v.title); b.type = "button";
      b.setAttribute("aria-pressed", k === chosen);
      b.onclick = () => { chosen = k; drawPresets(); fillForm(presets[k].brief); };
      box.append(b);
    });
  }

  function chips(box, items, picked) {
    box.replaceChildren();
    items.forEach(it => {
      const b = el("button", `chip${picked.includes(it.id) ? " on" : ""}`, it.label); b.type = "button";
      b.dataset.id = it.id; b.setAttribute("aria-pressed", picked.includes(it.id));
      b.onclick = () => { const on = b.classList.toggle("on"); b.setAttribute("aria-pressed", on); drawBrief(); };
      box.append(b);
    });
  }

  function fillForm(brief) {
    const recorded = state?.mode !== "live";
    $("#f-title").value = brief.title || ""; $("#f-title").readOnly = recorded;
    $("#f-title-note").hidden = !recorded; $("#f-skills-note").hidden = !recorded;
    // What Recorded can answer depends on the example: only the published
    // course has a recorded model behind it, and its outline is fixed.
    $("#f-skills-note").textContent = chosen === "course"
      ? "Recorded mode: the model always proposes this example's outline — three lessons and an exam. Change the skills or the count and the checks judge that outline against your choice; they do not change what it proposes. Live writes a new one."
      : "Recorded mode: this example is recorded only as far as its refusal. Fix what is refused and the run stops with nothing recorded for the outline — Live carries it on.";
    chips($("#f-audience"), form.audiences, brief.audience || []);
    chips($("#f-skills"), form.skills, brief.objectives || []);
    $("#f-minutes").value = brief.minutes_per_lesson ?? "";
    $("#f-nodes").value = brief.requested_nodes ?? "";
    drawBrief();
  }

  const picked = box => [...box.querySelectorAll(".chip.on")].map(b => b.dataset.id);
  const whole = v => (/^-?\d+$/.test(v.trim()) ? Number(v) : v.trim() || undefined);
  const text = v => v.trim() || undefined;            // an empty field is left out, as the server leaves it out

  function readForm() {
    const brief = { id: presets[chosen].brief.id, title: text($("#f-title").value), audience: picked($("#f-audience")),
      objectives: picked($("#f-skills")), minutes_per_lesson: whole($("#f-minutes").value),
      requested_nodes: whole($("#f-nodes").value) };
    Object.keys(brief).forEach(k => brief[k] === undefined && delete brief[k]);
    return brief;
  }

  // The JSON, one top-level field at a time, so the field a person just
  // changed can be lit up in the text the system receives.
  function drawBrief() {
    const brief = readForm(), pre = $("#drawer-brief"), keys = Object.keys(brief), was = shown;
    pre.replaceChildren(document.createTextNode("{\n"));
    shown = {};
    keys.forEach((k, i) => {
      const text = `  "${k}": ${JSON.stringify(brief[k], null, 2).replace(/\n/g, "\n  ")}`;
      shown[k] = text;
      pre.append(el("span", was[k] !== undefined && was[k] !== text ? "k hl" : "k", text), document.createTextNode(i < keys.length - 1 ? ",\n" : "\n"));
    });
    pre.append(document.createTextNode("}"));
    const lim = form.limits;
    $("#f-minutes-note").textContent = `the organisation allows up to ${lim.minutes_per_lesson}`;
    $("#f-nodes-note").textContent = `lessons and exam together; up to ${lim.requested_nodes}`;
    $("#f-audience-note").textContent = `checked against what you may author for; up to ${lim.audience} audiences`;
  }

  function openDrawer() {
    chosen = state?.preset || "course"; shown = {};
    drawPresets(); fillForm(presets[chosen].brief);
    $("#drawer").hidden = false; $("#scrim").hidden = false;
  }
  function closeDrawer() { $("#drawer").hidden = true; $("#scrim").hidden = true; }

  async function create() {
    const brief = readForm();
    closeDrawer(); quiet();
    working(true, "Reading the brief…");
    try {
      const reset = await api("reset", { mode: state.mode, preset: chosen });
      if (!reset.ok) { toast(reset.error, true); return; }
      seenStages = 0;
      const out = await api("submit", { brief });
      if (!out.ok) toast(out.error, true);
    } catch { /* refresh() below says the server is gone */ } finally { working(false); document.querySelectorAll("button").forEach(b => { b.dataset.was = ""; }); await refresh(); }
  }

  // ── a node in the lesson editor ─────────────────────────────────────
  function openEditor(n) {
    const c = n.content || {};
    $("#ed-crumb").replaceChildren(document.createTextNode(`${state.brief.title}  ›  `), el("b", "", n.type === "exam" ? "Exam" : words(n.skill)),
      document.createTextNode(`  ·  ${c.minutes ?? "—"} min${c.points_total != null ? ` · ${c.points_total} points` : ""}`));
    $("#ed-proposal").hidden = !(n.state === "Validated" && state.revision.state === "ContentInProgress");
    const outline = $("#ed-outline"); outline.replaceChildren();
    const canvas = $("#ed-canvas"); canvas.replaceChildren();
    (Array.isArray(c.blocks) ? c.blocks : []).forEach((b, i) => {
      outline.append(el("a", "", `${i + 1}. ${words(b.type)}`));
      const blk = el("div", `blk ${b.type}${n.state === "Validated" ? " added" : ""}${b.type === "callout" ? " tint" : ""}`);
      const label = el("span", "blk-label"); label.append(icon("pencil"), document.createTextNode(words(b.type))); blk.append(label);
      if (b.type === "heading") blk.append(el("h3", "", b.text));
      else if (b.text) blk.append(el("p", "", b.text));
      if (b.question) blk.append(el("p", "", b.question));
      if (Array.isArray(b.options)) { const ol = el("ol"); b.options.forEach((o, j) => ol.append(el("li", j === b.answer ? "right-answer" : "", o))); blk.append(ol); }
      if (Array.isArray(b.items)) { const ul = el("ul"); b.items.forEach(o => ul.append(el("li", "", o))); blk.append(ul); }
      if (b.type === "image") { blk.append(el("div", "ph", `image · ${b.src}`)); if (b.caption) blk.append(el("p", "muted", b.caption)); }
      const cites = [...(b.cites || []), ...(b.points != null ? [`${b.points} points`] : [])];
      if (cites.length) blk.append(el("div", "cites", cites.join(" · ")));
      canvas.append(blk);
    });
    $("#ed-approve").onclick = () => { $("#editor").close(); act("approve", { node: n.id }, "Recording the approval…"); };
    $("#ed-reject").onclick = () => {
      const reason = prompt("Why is this rejected? The next draft is told exactly this.");
      if (reason) { $("#editor").close(); act("reject", { node: n.id, reason }, "Recording the rejection…"); }
    };
    $("#editor").showModal();
  }

  // ── wiring ──────────────────────────────────────────────────────────
  document.querySelectorAll("[data-act]").forEach(b => b.addEventListener("click", () => act(b.dataset.act, {},
    { "approve-outline": "Committing the outline…", checks: "Running the whole-course checks…", sign: "Checking the approval chain…",
      publish: "Publishing…", release: "Releasing the course…" }[b.dataset.act])));

  // Starting over discards the course on screen, so it asks first once there is one.
  async function startOver(mode) {
    if (state.revision.state !== "AwaitingBrief" && !confirm("Start over? The course on screen is discarded.")) return;
    working(true, "Starting over…"); quiet();
    try {
      const out = await api("reset", { mode, preset: state.preset });
      if (out.ok) seenStages = 0; else toast(out.error, true);
    } catch { /* refresh() below says the server is gone */ } finally { working(false); document.querySelectorAll("button").forEach(b => { b.dataset.was = ""; }); await refresh(); }
  }
  document.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => {
    if (b.dataset.mode !== state.mode) startOver(b.dataset.mode);
  }));
  document.querySelectorAll("[data-tab]").forEach(t => t.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach(x => x.classList.toggle("on", x === t));
    document.querySelectorAll("[data-panel]").forEach(p => { p.hidden = p.dataset.panel !== t.dataset.tab; });
  }));
  $("#reset").addEventListener("click", () => startOver(state.mode));
  $("#reject-outline").addEventListener("click", () => {
    const reason = prompt("Why is this outline rejected? The model is told exactly this when it drafts again.");
    if (reason) act("reject-outline", { reason }, state.mode === "live" ? "Drafting a new outline…" : "Asking the recorded model again…");
  });
  $("#drawer-cancel").addEventListener("click", closeDrawer);
  $("#scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#drawer").hidden) closeDrawer(); });
  $("#create").addEventListener("click", create);
  ["#f-title", "#f-minutes", "#f-nodes"].forEach(id => $(id).addEventListener("input", drawBrief));
  $("#brief-form").addEventListener("submit", e => e.preventDefault());
  $("#ed-close").addEventListener("click", () => $("#editor").close());

  Promise.all([api("presets"), api("form")]).then(([p, f]) => { presets = p; form = f; refresh(); })
    .catch(() => toast("The page could not load the brief form. Restart make ui: the server is older than the page.", true));
})();
