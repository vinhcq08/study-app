// Subjects: what you're taking now, what's ready to start, what's done, and the rest by area.
// Also where you download and restore a backup of everything you've recorded.
import { downloadBackup, fetchTree, restoreBackup } from "./api.js";
import { initNav } from "./nav.js";
import { initTimer } from "./timer.js";
import { esc, inDays, plural, toast } from "./util.js";

const $ = (id) => document.getElementById(id);
const laneColor = (s) => `var(--${s.kind === "gap_filler" ? "gap" : s.lane_id})`;
const link = (s, extra = "") => `subject.html?id=${encodeURIComponent(s.id)}${extra}`;
let data = null;

function nowCard(s, lanes) {
  const exam = s.next_exam;
  return `<article class="now-card" style="--c:${laneColor(s)}" data-name="${esc(s.name.toLowerCase())}">
    <div class="nc-top">
      <div class="nc-name">
        <span class="eyebrow">${esc(lanes[s.lane_id].toUpperCase())}${s.semester ? ` · ${esc(s.semester)}` : ""}</span>
        <a href="${link(s)}"><h3>${esc(s.name)}</h3></a>
      </div>
      <span class="lvl" title="Level ${s.level} of 5"><small>LV</small><b>${s.level}</b></span>
    </div>
    <div class="nc-bar" role="img" aria-label="Mastery ${s.mastery_pct}%"><i style="width:${s.mastery_pct}%"></i></div>
    <dl class="nc-facts">
      <div><dt>Mastery</dt><dd>${s.mastery_pct}%${s.level < 5 ? ` <small>· level ${s.level + 1} at ${s.next_level_at}%</small>` : ""}</dd></div>
      <div><dt>Due for review</dt><dd>${s.due_count ? `<a href="${link(s, "&review=1")}">${plural(s.due_count, "topic")}</a>` : "Nothing due"}</dd></div>
      <div><dt>Next exam</dt><dd>${exam ? `${esc(exam.name)} <small>· ${inDays(exam.days_left)} · ${exam.readiness_pct}% ready</small>` : `<a href="${link(s)}#exams-section">Add a date</a>`}</dd></div>
      <div><dt>Past papers</dt><dd>${s.practice_total ? `<a href="${link(s)}#exams-section">${s.practice_done} of ${s.practice_total} done</a>` : "None listed"}</dd></div>
    </dl>
  </article>`;
}

function row(s, detail) {
  return `<li data-name="${esc(s.name.toLowerCase())}"><a href="${link(s)}" style="--c:${laneColor(s)}" class="${s.kind === "gap_filler" ? "gap" : ""}">
    <i aria-hidden="true"></i><span class="r-name">${esc(s.name)}</span>
    <span class="r-detail">${detail}</span></a></li>`;
}

function render() {
  const { subjects, lanes: laneList } = data;
  const lanes = Object.fromEntries(laneList.map((l) => [l.id, l.name]));
  const now = subjects.filter((s) => s.state === "in_progress");
  const ready = subjects.filter((s) => s.state === "ready");
  const done = subjects.filter((s) => s.state === "done");
  const later = subjects.filter((s) => s.state === "locked");
  const gap = (s) => (s.kind === "gap_filler" ? "MIT gap-filler · " : "");

  $("counts").textContent = `${plural(now.length, "subject")} in progress · ${done.length} done · ${subjects.length} in your plan`;
  $("now").innerHTML = now.length
    ? now.map((s) => nowCard(s, lanes)).join("")
    : `<p class="none">Nothing in progress. Pick one from “Ready to start” and set its status on the subject page.</p>`;
  $("ready").innerHTML = ready.map((s) => row(s, `${gap(s)}${esc(lanes[s.lane_id])}`)).join("")
    || `<li class="none">Nothing yet. Finish a prerequisite to unlock more.</li>`;
  $("done").innerHTML = done.map((s) => row(s, `${s.grade ? `Grade ${esc(s.grade)} · ` : ""}${s.semester ? `${esc(s.semester)} · ` : ""}${s.mastery_pct}% mastery`)).join("")
    || `<li class="none">No subjects marked done yet.</li>`;
  $("later").innerHTML = laneList.map((l) => {
    const items = later.filter((s) => s.lane_id === l.id);
    if (!items.length) return "";
    return `<details class="lane-group" style="--c:var(--${l.id})">
      <summary><b>${esc(l.name)}</b><small>${plural(items.length, "subject")}</small></summary>
      <ul class="rows">${items.map((s) => row(s, `${gap(s)}${s.semester ? esc(s.semester) : "Needs prerequisites"}`)).join("")}</ul>
    </details>`;
  }).join("");
  applySearch();
}

function applySearch() {
  const q = $("search").value.trim().toLowerCase();
  document.querySelectorAll("[data-name]").forEach((el) => { el.hidden = !!q && !el.dataset.name.includes(q); });
  document.querySelectorAll(".lane-group").forEach((g) => {
    const any = [...g.querySelectorAll("[data-name]")].some((el) => !el.hidden);
    g.hidden = !any;
    if (q) g.open = any;
  });
}

async function load() {
  try {
    data = await fetchTree();
    render();
  } catch (err) {
    $("counts").textContent = `Couldn't load your subjects: ${err.message}`;
  }
}

$("search").addEventListener("input", applySearch);

$("downloadBackup").addEventListener("click", async () => {
  try {
    const backup = await downloadBackup();
    const blob = new Blob([JSON.stringify(backup, null, 1)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob), download: `study-app-backup-${backup.exported_on}.json`,
    });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast("Backup downloaded.");
  } catch (err) {
    toast(`Couldn't make a backup: ${err.message}`, true);
  }
});

$("restoreFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  let backup;
  try { backup = JSON.parse(await file.text()); } catch { toast("That file isn't a Study App backup.", true); return; }
  const when = backup?.exported_on ? ` from ${backup.exported_on}` : "";
  if (!confirm(`Restore the backup${when}? This replaces everything recorded in this browser.`)) return;
  try {
    await restoreBackup(backup);
    toast("Backup restored.");
    load();
  } catch (err) {
    toast(err.message, true);
  }
});

initNav("subject");
initTimer();
load();
