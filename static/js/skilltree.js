// Skill Tree page: draws the curriculum graph and lets you track progress.
import { fetchOverview, fetchTree, saveProgress } from "./api.js";
import { initNav } from "./nav.js";
import { initTimer } from "./timer.js";
import { hoursAndMinutes, inDays } from "./util.js";

// ---- Layout constants (pixels) ----
const PADL = 170;   // space for lane labels on the left
const COLW = 198;   // width of one tier column
const NW = 164;     // node width
const NH = 50;      // node height
const ROWH = 62;    // height of one row
const HEAD = 36;    // space for tier labels at the top

const STATE_TEXT = {
  done: "Done",
  in_progress: "In progress",
  ready: "Ready to start",
  locked: "Prerequisites not done yet",
};
const MATCH = {
  strong: "Strong match",
  partial: "Partial match",
  extra: "Beyond MIT’s CS core",
  gap: "MIT subject you don’t have",
};
const MATCH_DESC = {
  strong: "MIT teaches an equivalent subject.",
  partial: "MIT covers this differently or only in part.",
  extra: "MIT puts this in an electrical engineering major, offers it only as an elective, or doesn’t teach it.",
  gap: "Not in your degree. Study it on MIT OpenCourseWare.",
};
const AI_TARGETS = ["ml", "dl", "genai", "cv"];
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- State ----
let lanes = [];
let subjects = {};      // id -> subject (from the API, including state)
let relations = [];
let overview = null;   // upcoming exams, weak spots and study time across subjects
let tiers = 0;
let rows = 0;
let W = 0;
let H = 0;
const ui = { showGaps: true, aiFocus: false, selected: null, query: "", scale: 1 };

// ---- DOM ----
const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const sizer = $("sizer");
const viewport = $("viewport");
const panel = $("panel");

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const isGap = (s) => s.kind === "gap_filler";
const visible = (s) => ui.showGaps || !isGap(s);
const colorOf = (s) => `var(--${isGap(s) ? "gap" : s.lane_id})`;
const nx = (s) => PADL + s.tier * COLW + (COLW - NW) / 2;
const ny = (s) => HEAD + s.grid_row * ROWH + (ROWH - NH) / 2;

function edgeKind(r) {
  if (r.kind === "related") return "rel";
  if (r.kind === "supports" || isGap(subjects[r.from_id]) || isGap(subjects[r.to_id])) return "gap";
  return "pre";
}
const visibleRelations = () => relations.filter((r) => visible(subjects[r.from_id]) && visible(subjects[r.to_id]));

// ---- Drawing ----
function pathFor(r) {
  let a = subjects[r.from_id];
  let b = subjects[r.to_id];
  if (a.tier > b.tier) [a, b] = [b, a];
  const sx = nx(a) + NW;
  const sy = ny(a) + NH / 2;
  if (a.tier === b.tier) {
    // Same column: loop out to the right and back in.
    const ey = ny(b) + NH / 2;
    const bx = sx + 26;
    return `M${sx} ${sy} C${bx} ${sy} ${bx} ${ey} ${sx} ${ey}`;
  }
  const ex = nx(b) - 2;
  const ey = ny(b) + NH / 2;
  const dx = (ex - sx) / 2;
  return `M${sx} ${sy} C${sx + dx} ${sy} ${ex - dx} ${ey} ${ex} ${ey}`;
}

function nodeCode(s) {
  if (isGap(s)) return `Gap · MIT ${s.mit_code}`;
  if (s.mit_match === "extra") return s.mit_code ? `Extra · ${s.mit_code}` : "Not at MIT";
  if (s.mit_match === "partial") return `≈ MIT ${s.mit_code}`;
  return `MIT ${s.mit_code}`;
}

function buildCanvas() {
  canvas.style.width = `${W}px`;
  canvas.style.height = `${H}px`;
  let html = "";
  lanes.forEach((l, i) => {
    const top = HEAD + l.row_start * ROWH;
    const h = (l.row_end - l.row_start + 1) * ROWH;
    const count = Object.values(subjects).filter((s) => s.lane_id === l.id && !isGap(s)).length;
    html += `<div class="band${i % 2 ? " alt" : ""}" style="top:${top}px;height:${h}px"></div>`;
    html += `<div class="lane-label" style="--c:var(--${l.id});top:${top + 12}px">${esc(l.name)}<small>${count} subject${count === 1 ? "" : "s"}</small></div>`;
  });
  for (let t = 0; t < tiers; t++) {
    html += `<div class="tier" style="left:${PADL + t * COLW + (COLW - NW) / 2}px">TIER ${t + 1}</div>`;
  }
  html += `<svg class="edges" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true">
    <defs>
      <marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="var(--edge)"/></marker>
      <marker id="arrOn" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="var(--ink)"/></marker>
    </defs>
    ${relations.map((r, i) => {
      const k = edgeKind(r);
      return `<path id="e${i}" class="k-${k}" d="${pathFor(r)}"${k === "rel" ? "" : ' marker-end="url(#arr)"'}/>`;
    }).join("")}
  </svg>`;
  for (const s of Object.values(subjects)) {
    html += `<button class="node${isGap(s) ? " gap" : ""}" id="n-${s.id}" data-id="${s.id}"
      style="--c:${colorOf(s)};left:${nx(s)}px;top:${ny(s)}px" title="${esc(s.name)}">
      <span class="nm">${esc(s.short_name)}</span><span class="cd">${esc(nodeCode(s))}</span><span class="st"></span><span class="mb"><i></i></span></button>`;
  }
  canvas.innerHTML = html;
}

// ---- Graph walks ----
function ancestors(id, set = new Set()) {
  for (const r of visibleRelations()) {
    if (r.kind !== "related" && r.to_id === id && !set.has(r.from_id)) {
      set.add(r.from_id);
      ancestors(r.from_id, set);
    }
  }
  return set;
}
function descendants(id, set = new Set()) {
  for (const r of visibleRelations()) {
    if (r.kind !== "related" && r.from_id === id && !set.has(r.to_id)) {
      set.add(r.to_id);
      descendants(r.to_id, set);
    }
  }
  return set;
}

function matchesQuery(s) {
  const q = ui.query.trim().toLowerCase();
  if (!q) return true;
  return [s.name, s.short_name, s.mit_code, s.ocw_code].some((v) => v && v.toLowerCase().includes(q));
}

// ---- Refresh classes after any change ----
function refresh() {
  let focus = null;
  let edgeOn = () => false;
  const sel = ui.selected;

  if (sel) {
    const up = ancestors(sel); up.add(sel);
    const down = descendants(sel); down.add(sel);
    focus = new Set([...up, ...down]);
    for (const r of visibleRelations()) {
      if (r.kind === "related" && (r.from_id === sel || r.to_id === sel)) { focus.add(r.from_id); focus.add(r.to_id); }
    }
    edgeOn = (r) => r.kind === "related"
      ? r.from_id === sel || r.to_id === sel
      : (up.has(r.from_id) && up.has(r.to_id)) || (down.has(r.from_id) && down.has(r.to_id));
  } else if (ui.aiFocus) {
    focus = new Set(AI_TARGETS);
    AI_TARGETS.forEach((t) => ancestors(t, focus));
    edgeOn = (r) => r.kind !== "related" && focus.has(r.from_id) && focus.has(r.to_id);
  } else if (ui.query.trim()) {
    focus = new Set(Object.values(subjects).filter(matchesQuery).map((s) => s.id));
  }

  for (const s of Object.values(subjects)) {
    const el = $(`n-${s.id}`);
    el.hidden = !visible(s);
    el.classList.remove("done", "in_progress", "ready", "locked");
    el.classList.add(s.state);
    el.classList.toggle("sel", sel === s.id);
    el.classList.toggle("dim", !!focus && !focus.has(s.id));
    el.setAttribute("aria-pressed", String(sel === s.id));
    el.setAttribute("aria-label", `${s.name}. ${STATE_TEXT[s.state]}. ${s.mastery_pct}% topic mastery. ${MATCH[s.mit_match]}.`);
    el.querySelector(".mb i").style.width = `${s.mastery_pct}%`;
    el.classList.toggle("has-mastery", s.mastery_pct > 0);
  }
  relations.forEach((r, i) => {
    const p = $(`e${i}`);
    const vis = visible(subjects[r.from_id]) && visible(subjects[r.to_id]);
    p.style.display = vis ? "" : "none";
    const on = vis && edgeOn(r);
    p.classList.toggle("on", on);
    p.classList.toggle("off", !!focus && !on);
    if (r.kind !== "related") p.setAttribute("marker-end", on ? "url(#arrOn)" : "url(#arr)");
  });
  renderPanel();
  renderStats();
}

// ---- Panel ----
const chip = (id) => {
  const s = subjects[id];
  return `<button class="chip${isGap(s) ? " gap" : ""}" data-go="${id}" style="--c:${colorOf(s)}"><i></i>${esc(s.short_name)}</button>`;
};
const chipList = (ids) => (ids.length ? `<div class="chips">${ids.map(chip).join("")}</div>` : '<p class="none">None</p>');

function nextUp() {
  const all = Object.values(subjects);
  const courses = all.filter((s) => !isGap(s) && s.state === "ready").sort((a, b) => a.tier - b.tier || a.grid_row - b.grid_row);
  const prio = { High: 0, Medium: 1 };
  const gaps = all.filter((s) => isGap(s) && s.state === "ready" && visible(s)).sort((a, b) => (prio[a.priority] ?? 2) - (prio[b.priority] ?? 2));
  return [...courses.slice(0, 5), ...gaps.slice(0, 2)].map((s) => s.id);
}

function renderOverview() {
  const all = Object.values(subjects);
  const courses = all.filter((s) => !isGap(s));
  const gaps = all.filter(isGap);
  const count = (st) => courses.filter((s) => s.state === st).length;
  panel.style.removeProperty("--c");
  panel.innerHTML = `
    <h2>Your progress</h2>
    <div class="progress">
      <div><b>${count("done")}<small> / ${courses.length}</small></b><span>Subjects done</span></div>
      <div><b>${count("in_progress")}</b><span>In progress</span></div>
      <div><b>${count("ready")}</b><span>Ready to start</span></div>
      <div><b>${overview ? overview.practice_done : "–"}<small> / ${overview ? overview.practice_total : "–"}</small></b><span>Practice exams done</span></div>
    </div>
    ${overview ? `<p class="none">Studied ${hoursAndMinutes(overview.minutes_this_week)} this week · ${overview.due_total} topic${overview.due_total === 1 ? "" : "s"} due for review · ${gaps.filter((s) => s.state === "done").length} of ${gaps.length} gap-fillers done</p>` : ""}
    ${overview && overview.upcoming_exams.length ? `<h3>Upcoming exams</h3><ul class="ov-list">${overview.upcoming_exams.map((e) => `
      <li><a href="subject.html?id=${encodeURIComponent(e.subject_id)}">${esc(e.name)} · ${esc(e.subject_name)}</a>
        <small>${inDays(e.days_left)} · ${e.readiness_pct}% ready</small></li>`).join("")}</ul>` : ""}
    ${overview && overview.weak_spots.length ? `<h3>Needs attention</h3><ul class="ov-list">${overview.weak_spots.map((t) => `
      <li><a href="subject.html?id=${encodeURIComponent(t.subject_id)}#t-${encodeURIComponent(t.id)}">${esc(t.name)}</a>
        <small>${esc(t.subject_name)} · ${esc(t.weak_reasons.join(", "))}</small></li>`).join("")}</ul>` : ""}
    <h3>Next up</h3>
    ${chipList(nextUp())}
    <p class="none">Select any subject in the tree to mark it in progress or done. A subject becomes ready once all its prerequisites are done.</p>
    <h3>Legend</h3>
    <div class="legend">
      <div><span class="sw done"></span>Done</div>
      <div><span class="sw doing"></span>In progress</div>
      <div><span class="sw"></span>Ready to start</div>
      <div><span class="sw locked"></span>Prerequisites not done</div>
      <div><span class="sw gap"></span>MIT gap-filler (self-study)</div>
      <div><span class="ln"></span>Prerequisite</div>
      <div><span class="ln rel"></span>Closely related</div>
      <div><span class="ln gap"></span>Gap-filler link</div>
    </div>`;
}

function renderDetail(s) {
  const lane = lanes.find((l) => l.id === s.lane_id);
  const vis = visibleRelations();
  const needs = vis.filter((r) => r.kind !== "related" && r.to_id === s.id).map((r) => r.from_id);
  const unlocks = vis.filter((r) => r.kind !== "related" && r.from_id === s.id).map((r) => r.to_id);
  const related = vis.filter((r) => r.kind === "related" && (r.from_id === s.id || r.to_id === s.id))
    .map((r) => (r.from_id === s.id ? r.to_id : r.from_id));
  const href = s.link_url || (s.ocw_code ? `https://ocw.mit.edu/search/?q=${encodeURIComponent(s.ocw_code)}` : null);
  const linkText = s.link_text || (s.ocw_code ? `Find ${s.ocw_code} on MIT OpenCourseWare` : "");

  panel.style.setProperty("--c", colorOf(s));
  panel.innerHTML = `
    <div class="p-lane">${isGap(s) ? "MIT GAP-FILLER" : esc(lane.name.toUpperCase())} · TIER ${s.tier + 1}</div>
    <h2>${esc(s.name)}</h2>
    <div class="seg" role="group" aria-label="Status">
      <button data-status="not_started" aria-pressed="${s.status === "not_started"}">Not started</button>
      <button data-status="in_progress" aria-pressed="${s.status === "in_progress"}">In progress</button>
      <button data-status="done" aria-pressed="${s.status === "done"}">Done</button>
    </div>
    <p class="none">${STATE_TEXT[s.state]}${isGap(s) ? " · Self-study" : ""}</p>
    <div class="fields">
      <label class="field">Semester<input id="f-semester" value="${esc(s.semester)}" placeholder="e.g. Year 1 · Sem 1" maxlength="30"></label>
      <label class="field">Grade<input id="f-grade" value="${esc(s.grade)}" placeholder="e.g. A" maxlength="10"></label>
    </div>
    <p class="saved" id="saved"></p>
    <a class="btn primary" href="subject.html?id=${encodeURIComponent(s.id)}">Open topic dashboard</a>
    <div class="lvl-row"><span class="lvl" title="Level ${s.level} of 5"><small>LV</small><b>${s.level}</b></span>
      <span>${s.mastery_pct}% topic mastery across ${s.topic_count} topics<br><small class="none">${s.next_level_at ? `${s.next_level_at - s.mastery_pct}% more to reach level ${s.level + 1}` : "Top level reached"}</small></span></div>
    ${s.due_count || s.practice_total ? `<h3>Do next</h3><div class="donext">
      ${s.due_count ? `<a class="btn" href="subject.html?id=${encodeURIComponent(s.id)}&filter=due">Review ${s.due_count} due topic${s.due_count === 1 ? "" : "s"}</a>` : ""}
      ${s.practice_total ? `<a class="btn" href="subject.html?id=${encodeURIComponent(s.id)}#practice-exams">Practice exams · ${s.practice_done} of ${s.practice_total} done</a>` : ""}
    </div>` : ""}
    <dl class="kv">
      <dt>MIT</dt><dd>${esc(s.mit_title)}</dd>
      <dt>Match</dt><dd><span class="pill ${s.mit_match}">${MATCH[s.mit_match]}</span><br><span class="none">${MATCH_DESC[s.mit_match]}</span></dd>
      ${href ? `<dt>Study</dt><dd><a href="${esc(href)}" target="_blank" rel="noopener">${esc(linkText)}</a></dd>` : ""}
    </dl>
    <p style="font-size:14px">${esc(s.note)}</p>
    <h3>Needs</h3>${chipList(needs)}
    <h3>Unlocks</h3>${chipList(unlocks)}
    ${related.length ? `<h3>Closely related</h3>${chipList(related)}` : ""}
    <button class="linkbtn" id="back">Back to overview</button>`;
}

function renderPanel() {
  const s = ui.selected && subjects[ui.selected];
  if (s) renderDetail(s); else renderOverview();
}

function renderStats() {
  const courses = Object.values(subjects).filter((s) => !isGap(s));
  const c = (m) => courses.filter((s) => s.mit_match === m).length;
  const done = courses.filter((s) => s.state === "done").length;
  $("stats").innerHTML = `
    <span><b>${done}/${courses.length}</b>subjects done</span>
    <span><b>${c("strong")}</b>strong MIT matches</span>
    <span><b>${c("partial")}</b>partial matches</span>
    <span><b>${c("extra")}</b>beyond MIT's CS core</span>
    <span><b>${Object.values(subjects).filter(isGap).length}</b>MIT gaps to fill</span>`;
}

// ---- Saving ----
let toastTimer;
function toast(msg, isError = false) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.toggle("error", isError);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 6000 : 4000);
}

async function save(id, changes) {
  const s = subjects[id];
  const body = {
    status: changes.status ?? s.status,
    semester: changes.semester ?? s.semester ?? null,
    grade: changes.grade ?? s.grade ?? null,
  };
  try {
    const result = await saveProgress(id, body);
    await reload();
    const savedEl = $("saved");
    if (savedEl && ui.selected === id) savedEl.textContent = "Saved";
    if (result.unlocked.length) {
      const names = result.unlocked.map((u) => subjects[u].short_name);
      toast(`Unlocked: ${names.join(", ")}`);
      for (const u of result.unlocked) {
        const el = $(`n-${u}`);
        el.classList.remove("pulse"); void el.offsetWidth; el.classList.add("pulse");
      }
    }
  } catch (err) {
    toast(`Couldn't save: ${err.message}. Check that the server is running.`, true);
  }
}

async function loadOverview() {
  try { overview = await fetchOverview(); } catch { overview = null; }
}

async function reload() {
  await loadOverview();
  const data = await fetchTree();
  subjects = Object.fromEntries(data.subjects.map((s) => [s.id, s]));
  relations = data.relations;
  lanes = data.lanes;
  refresh();
}

// ---- Selection, zoom, events ----
function select(id, { scroll = false, toggle = false } = {}) {
  if (!visible(subjects[id])) {
    ui.showGaps = true;
    $("tGaps").setAttribute("aria-pressed", "true");
  }
  ui.selected = toggle && ui.selected === id ? null : id;
  refresh();
  if (!ui.selected) return;
  const behavior = reduceMotion ? "auto" : "smooth";
  if (scroll) {
    const r = $(`n-${id}`).getBoundingClientRect();
    const v = viewport.getBoundingClientRect();
    if (r.left < v.left || r.right > v.right || r.top < v.top || r.bottom > v.bottom) {
      viewport.scrollTo({
        left: viewport.scrollLeft + (r.left - v.left) - v.width / 2 + r.width / 2,
        top: viewport.scrollTop + (r.top - v.top) - v.height / 2 + r.height / 2,
        behavior,
      });
    }
  } else if (window.innerWidth < 1040 && panel.getBoundingClientRect().top > window.innerHeight) {
    panel.scrollIntoView({ block: "start", behavior });
  }
}

function applyScale() {
  canvas.style.transform = `scale(${ui.scale})`;
  sizer.style.width = `${W * ui.scale}px`;
  sizer.style.height = `${H * ui.scale}px`;
}
function fit() {
  ui.scale = Math.max(0.5, Math.min(1, (viewport.clientWidth - 2) / W));
  applyScale();
}

canvas.addEventListener("click", (e) => {
  const node = e.target.closest(".node");
  if (node) select(node.dataset.id, { toggle: true });
  else if (ui.selected) { ui.selected = null; refresh(); }
});

panel.addEventListener("click", (e) => {
  const statusBtn = e.target.closest("[data-status]");
  if (statusBtn && ui.selected) { save(ui.selected, { status: statusBtn.dataset.status }); return; }
  const go = e.target.closest("[data-go]");
  if (go) { select(go.dataset.go, { scroll: true }); return; }
  if (e.target.id === "back") { ui.selected = null; refresh(); }
});

panel.addEventListener("change", (e) => {
  if (!ui.selected) return;
  if (e.target.id === "f-semester") save(ui.selected, { semester: e.target.value });
  if (e.target.id === "f-grade") save(ui.selected, { grade: e.target.value });
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && ui.selected) { ui.selected = null; refresh(); }
});

$("tGaps").addEventListener("click", (e) => {
  ui.showGaps = !ui.showGaps;
  e.currentTarget.setAttribute("aria-pressed", String(ui.showGaps));
  if (ui.selected && !visible(subjects[ui.selected])) ui.selected = null;
  refresh();
});
$("tAI").addEventListener("click", (e) => {
  ui.aiFocus = !ui.aiFocus;
  e.currentTarget.setAttribute("aria-pressed", String(ui.aiFocus));
  if (ui.aiFocus) ui.selected = null;
  refresh();
});
$("search").addEventListener("input", (e) => {
  ui.query = e.target.value;
  if (ui.query) { ui.selected = null; ui.aiFocus = false; $("tAI").setAttribute("aria-pressed", "false"); }
  refresh();
});
$("search").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  const first = Object.values(subjects).filter((s) => visible(s) && matchesQuery(s)).sort((a, b) => a.tier - b.tier)[0];
  if (first) { ui.query = ""; e.target.value = ""; select(first.id, { scroll: true }); }
});
$("zIn").addEventListener("click", () => { ui.scale = Math.min(1.4, +(ui.scale + 0.1).toFixed(2)); applyScale(); });
$("zOut").addEventListener("click", () => { ui.scale = Math.max(0.4, +(ui.scale - 0.1).toFixed(2)); applyScale(); });
$("zFit").addEventListener("click", fit);
window.addEventListener("resize", () => { if (viewport.clientWidth < W * ui.scale) fit(); });

// ---- Start ----
async function start() {
  try {
    const data = await fetchTree();
    lanes = data.lanes;
    relations = data.relations;
    subjects = Object.fromEntries(data.subjects.map((s) => [s.id, s]));
    tiers = Math.max(...data.subjects.map((s) => s.tier)) + 1;
    rows = Math.max(...lanes.map((l) => l.row_end)) + 1;
    W = PADL + tiers * COLW + 10;
    H = HEAD + rows * ROWH + 10;
    await loadOverview();
    buildCanvas();
    fit();
    refresh();
    const fromHash = decodeURIComponent(location.hash.slice(1));
    if (subjects[fromHash]) select(fromHash, { scroll: true });
  } catch (err) {
    panel.innerHTML = `<h2>Couldn't load your tree</h2><p class="none">${esc(err.message)}. Start the server with <code>uvicorn app.main:app --reload</code> and reload this page.</p>`;
  }
}
initNav("tree");
initTimer(() => reload());
start();
