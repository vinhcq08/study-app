// Subjects page tabs: the semester plan and your grades.
import { esc, plural } from "./util.js";

const laneColor = (s) => `var(--${s.kind === "gap_filler" ? "gap" : s.lane_id})`;
const link = (id) => `subject.html?id=${encodeURIComponent(id)}`;
const DEFAULT_SEMESTERS = [1, 2, 3, 4].flatMap((y) => [1, 2].map((t) => `Year ${y} · Sem ${t}`));
const STATUS = { done: "Done", in_progress: "In progress" };

function semesterSelect(s, names, label) {
  const options = [...DEFAULT_SEMESTERS, ...names.filter((n) => !DEFAULT_SEMESTERS.includes(n))];
  return `<select data-semester="${esc(s.id)}" aria-label="${esc(label)}">
    <option value="">${s.semester ? "Not planned" : "Plan for…"}</option>
    ${options.map((n) => `<option${n === s.semester ? " selected" : ""}>${esc(n)}</option>`).join("")}
  </select>`;
}

export function renderPlan(el, plan) {
  const names = plan.semesters.map((s) => s.name);
  const flagged = new Set(plan.warnings.map((w) => w.subject_id));
  const item = (s) => `<li class="${flagged.has(s.id) ? "warn" : ""}" style="--c:${laneColor(s)}">
      <i class="${s.kind === "gap_filler" ? "gap" : ""}" aria-hidden="true"></i>
      <span class="sp-name"><a href="${link(s.id)}">${esc(s.name)}</a>
        <small>${[STATUS[s.status], s.grade && `Grade ${esc(s.grade)}`, flagged.has(s.id) && "Check prerequisites"].filter(Boolean).join(" · ")}</small></span>
      ${s.status === "done" ? "" : semesterSelect(s, names, `Semester for ${s.name}`)}
    </li>`;
  el.innerHTML = `
    <p class="s-intro">Choose a semester for each subject you haven't finished. You'll be warned when a subject comes before something it needs.</p>
    ${plan.warnings.length ? `<div class="plan-warn" role="status">
      <h2>Check the order <small>${plural(plan.warnings.length, "issue")}</small></h2>
      <ul>${plan.warnings.map((w) => `<li>${esc(w.text)}</li>`).join("")}</ul></div>` : ""}
    ${plan.semesters.length ? `<div class="sem-grid">${plan.semesters.map((sem) => `
      <section class="sem">
        <h2>${esc(sem.name)} <small>${plural(sem.subjects.length, "subject")}</small></h2>
        <ul class="sem-list">${sem.subjects.map(item).join("")}</ul>
      </section>`).join("")}</div>` : `<p class="none">Nothing planned yet. Pick a semester for a subject below.</p>`}
    <details class="unplanned" open>
      <summary><b>Not planned yet</b> <small>${plural(plan.unplanned.length, "subject")}, in prerequisite order</small></summary>
      <ul class="sem-list">${plan.unplanned.map(item).join("")}</ul>
    </details>`;
}

const fmt = (n) => (n == null ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(2));

export function renderGrades(el, grades, subjects) {
  const o = grades.overall;
  const points = Object.fromEntries([...grades.graded, ...grades.not_counted].map((g) => [g.id, g]));
  const rows = subjects.filter((s) => s.status !== "not_started" || s.grade)
    .sort((a, b) => (a.status === b.status ? a.tier - b.tier : a.status === "done" ? -1 : 1));
  el.innerHTML = `
    <div class="g-kpis">
      <div class="g-kpi"><span class="label">GPA</span>
        <span class="value">${fmt(o.gpa)}${o.gpa != null ? "<small> / 4.0</small>" : ""}</span>
        <span class="sub">${o.letter_count ? `From ${plural(o.letter_count, "letter grade")}, unweighted` : "Enter letter grades below to see it"}</span></div>
      ${o.number_count ? `<div class="g-kpi"><span class="label">Average mark</span>
        <span class="value">${fmt(o.average)}<small> / ${o.out_of}</small></span>
        <span class="sub">From ${plural(o.number_count, "numeric grade")}</span></div>` : ""}
    </div>
    ${grades.by_lane.length ? `<section class="card">
      <h2>By area</h2>
      <ul class="g-lanes">${grades.by_lane.map((l) => `<li style="--c:var(--${l.lane_id})">
        <span class="g-lane">${esc(l.name)} <small>${plural(l.count, "subject")}</small></span>
        <span class="g-bar" role="img" aria-label="${esc(l.name)}: GPA ${fmt(l.gpa)}"><i style="width:${l.gpa != null ? (100 * l.gpa) / 4 : 0}%"></i></span>
        <b>${l.gpa != null ? fmt(l.gpa) : `${fmt(l.average)} / ${l.out_of}`}</b></li>`).join("")}</ul>
    </section>` : ""}
    <section class="card">
      <h2>Your grades</h2>
      ${rows.length ? `<ul class="g-rows">${rows.map((s) => {
        const g = points[s.id];
        const note = g?.points != null ? `${fmt(g.points)} points` : grades.not_counted.some((n) => n.id === s.id) ? "Not counted" : "";
        return `<li style="--c:${laneColor(s)}"><i aria-hidden="true"></i>
          <span class="sp-name"><a href="${link(s.id)}">${esc(s.name)}</a><small>${STATUS[s.status] || "Not started"}${s.semester ? ` · ${esc(s.semester)}` : ""}</small></span>
          <small class="g-note">${note}</small>
          <input data-grade="${esc(s.id)}" value="${esc(s.grade || "")}" maxlength="10" placeholder="Grade" aria-label="Grade for ${esc(s.name)}">
        </li>`;
      }).join("")}</ul>` : `<p class="none">Grades appear here for subjects in progress or done.</p>`}
      <p class="none">Letter grades use the common 4.0 scale: ${esc(grades.scale)}. Your university's scale may differ slightly. Numbers are averaged separately. Every subject counts equally, because credits aren't recorded.</p>
    </section>`;
}
