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
    Planned: ["", "Planned"], ContentDrafting: ["work", "Drafting"], Generated: ["work", "Drafting"],
    OutputGuardrail: ["work", "Screening"], NodeChecks: ["work", "Checking"], Validated: ["review", "Awaiting review"],
    NodeApproved: ["ok", "Approved"], NeedsRevalidation: ["work", "Re-checking"], NodeRepair: ["bad", "Needs a person"],
    NodeRecovery: ["bad", "Recovering"], BlockedFinal: ["bad", "Blocked"], Removed: ["", "Removed"],
  };

  const $ = s => document.querySelector(s);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const icon = (id, cls = "ico") => { const ns = "http://www.w3.org/2000/svg"; const s = document.createElementNS(ns, "svg"); s.setAttribute("class", cls); const u = document.createElementNS(ns, "use"); u.setAttribute("href", `#i-${id}`); s.append(u); return s; };
  const words = s => (s || "").replace(/[-_]/g, " ").replace(/^./, c => c.toUpperCase());
  let state = null, presets = {}, chosen = "course", seenStages = 0;

  async function api(path, body) {
    const r = await fetch(`/api/${path}`, body === undefined ? {} :
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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

  async function act(name, body = {}, title = "Working…") {
    working(true, title);
    try {
      const out = await api(name, body);
      if (!out.ok) toast(out.error, true);
    } finally { working(false); document.querySelectorAll("button").forEach(b => { b.dataset.was = ""; }); await refresh(); }
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
    const lastEngine = s.engine_log[s.engine_log.length - 1];
    // Who stopped it, in the order a reader looks: a screening that denied, an
    // engine's refusal with its artifact, then whatever reason the machine kept.
    const refused = BAD.has(st) ? (lastStage(s, /^(deny|unreachable|effect)/)
      || (lastEngine && `${lastEngine.engine} — ${lastEngine.summary}`) || s.revision.last_refusal) : null;
    why.hidden = !refused; why.textContent = refused ? `Stopped at ${st} · ${refused}` : "";

    if (!s.nodes.length) {
      const empty = el("div", "empty");
      const tile = el("div", "tile"); tile.append(icon("sparkles"));
      empty.append(tile, el("b", "", st === "AwaitingBrief" ? "Create this course with AI" : "No outline yet"),
        el("span", "muted", st === "AwaitingBrief" ? "Describe the course; the model drafts an outline, and nothing reaches a learner until a person approves it."
          : "The brief did not get as far as an outline."));
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

    const working = st === "ContentInProgress";
    s.nodes.forEach(n => {
      const row = el("div", "row child");
      const t = el("div", `tile ${n.type === "exam" ? "t-exam" : "t-topic"}`); t.append(icon(n.type === "exam" ? "quiz" : "file"));
      const m = el("div", "row-main");
      const title = el("div", "row-title", n.type === "exam" ? "Exam" : words(n.skill));
      const [pc, pl] = NODE_PILL[n.state] || ["", n.state];
      title.append(el("span", `pill ${pc}`, pl));
      if (n.repairs) title.append(el("span", "pill bad", `${n.repairs} repair${n.repairs > 1 ? "s" : ""}`));
      m.append(title, el("div", "row-sub", n.type === "exam" ? `${n.id} · over ${(n.topics || []).join(", ")}` : n.id));
      if (n.last_refusal && !["NodeApproved", "Validated"].includes(n.state)) m.append(el("div", "row-why", `refused: ${n.last_refusal}`));
      const actions = el("div", "row-actions");
      const btn = (cls, ic, label, on) => { const b = el("button", `btn sm ${cls}`); b.type = "button"; b.append(icon(ic), document.createTextNode(label)); b.onclick = on; actions.append(b); };
      if (working && ["Planned", "ContentDrafting", "OutputGuardrail"].includes(n.state))
        btn("primary", "sparkles", "Generate", () => act("generate", { node: n.id }, `Writing ${n.type === "exam" ? "the exam" : words(n.skill)}…`));
      if (n.content) btn("ghost", "eye", n.state === "Validated" ? "Review" : "View", () => openEditor(n));
      if (working && n.state === "Validated") btn("outline", "check", "Approve", () => act("approve", { node: n.id }, "Recording the approval…"));
      row.append(icon("grip", "grip"), t, m, actions);
      tree.append(row);
    });
  }

  function lastStage(s, re) { const hit = [...s.stages].reverse().find(x => re.test(String(x[3]))); return hit ? `${hit[1]} — ${hit[3]}` : ""; }

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
    if (!s.engine_log.length) eng.append(el("li", "muted", "Nothing refused yet."));
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
  function drawPresets() {
    const box = $("#presets"); box.replaceChildren();
    Object.entries(presets).forEach(([k, v]) => {
      const r = el("div", `radio${k === chosen ? " on" : ""}`); r.tabIndex = 0;
      const text = el("div"); text.append(el("b", "", v.title), el("small", "", v.brief.title));
      r.append(el("span", "dot"), text);
      r.onclick = () => { chosen = k; drawPresets(); };
      box.append(r);
    });
    $("#drawer-brief").textContent = JSON.stringify(presets[chosen].brief, null, 2);
  }
  function openDrawer() { chosen = state?.preset || "course"; drawPresets(); $("#drawer").hidden = false; $("#scrim").hidden = false; }
  function closeDrawer() { $("#drawer").hidden = true; $("#scrim").hidden = true; }

  async function create() {
    closeDrawer();
    working(true, "Reading the brief…");
    try {
      const reset = await api("reset", { mode: state.mode, preset: chosen });
      if (!reset.ok) { toast(reset.error, true); return; }
      seenStages = 0;
      const out = await api("submit", { brief: presets[chosen].brief });
      if (!out.ok) toast(out.error, true);
    } finally { working(false); document.querySelectorAll("button").forEach(b => { b.dataset.was = ""; }); await refresh(); }
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
    working(true, "Starting over…");
    try {
      const out = await api("reset", { mode, preset: state.preset });
      if (!out.ok) toast(out.error, true);
      seenStages = 0;
    } finally { working(false); document.querySelectorAll("button").forEach(b => { b.dataset.was = ""; }); await refresh(); }
  }
  document.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => {
    if (b.dataset.mode !== state.mode) startOver(b.dataset.mode);
  }));
  document.querySelectorAll("[data-tab]").forEach(t => t.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach(x => x.classList.toggle("on", x === t));
    document.querySelectorAll("[data-panel]").forEach(p => { p.hidden = p.dataset.panel !== t.dataset.tab; });
  }));
  $("#reset").addEventListener("click", () => startOver(state.mode));
  $("#drawer-cancel").addEventListener("click", closeDrawer);
  $("#scrim").addEventListener("click", closeDrawer);
  $("#create").addEventListener("click", create);
  $("#ed-close").addEventListener("click", () => $("#editor").close());

  api("presets").then(p => { presets = p; refresh(); });
})();
