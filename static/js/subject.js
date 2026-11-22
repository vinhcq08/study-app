// Subject dashboard: topics, mastery, reviews, exams, practice exams, flashcards and study time.
import {
  addCard, addExam, addResource, deleteCard, deleteExam, deleteResource,
  fetchDashboard, saveProgress, tickPracticeExam, updateTopic,
} from "./api.js";
import { initNav } from "./nav.js";
import { openPaperResult, resultText } from "./paper-result.js";
import { openPractice } from "./practice.js";
import { openReview } from "./review.js";
import { activeTopic, initTimer, startTimer } from "./timer.js";
import { ago, daysBetween, esc, hoursAndMinutes, inDays, longDate, plural, shortDate, toast } from "./util.js";

const STATE_TEXT = {
  done: "Done",
  in_progress: "In progress",
  ready: "Ready to start",
  locked: "Prerequisites not done yet",
};
const FILTERS = [
  ["all", "All", () => true],
  ["not_started", "Not started", (t) => t.mastery === 0],
  ["learning", "In progress", (t) => t.mastery > 0 && t.mastery < 4],
  ["mastered", "Mastered", (t) => t.mastery === 4],
  ["due", "Due for review", (t) => t.is_due],
  ["exam", "On next exam", (t) => t.on_next_exam],
  ["attention", "Needs attention", (t) => t.weak_reasons.length > 0],
  ["ai", "★ Key for AI", (t) => t.ai_key],
];
const KIND_LABEL = { final: "End of subject", midterm: "Midterm", quiz: "Quiz", practice: "Practice set" };
const RESOURCE_KINDS = [["video", "Video"], ["reading", "Reading"], ["slides", "Slides"], ["exercises", "Exercises"], ["other", "Other"]];
const BAR_ORDER = [4, 3, 2, 1, 0];

const params = new URLSearchParams(location.search);
const subjectId = params.get("id");
if (!subjectId) location.replace("subjects.html");
let data = null;
let filter = new URLSearchParams(location.search).get("filter") || "all";
let showExamForm = false;
const openDetails = new Set();

const $ = (id) => document.getElementById(id);
const laneColor = (s) => `var(--${s.kind === "gap_filler" ? "gap" : s.lane_id})`;
const allTopics = () => data.units.flatMap((u) => u.topics);
const topicById = (id) => allTopics().find((t) => t.id === id);
const practiceById = (id) => data.practice_exams.find((e) => e.id === id);
const levelName = (l) => data.mastery_labels[l];
const unitNames = () => Object.fromEntries(data.units.map((u) => [u.id, u.name]));

async function askPaperResult(exam) {
  const saved = await openPaperResult(exam, data.units);
  if (saved) {
    await reload();
    toast(saved.weak_units.length ? "Result saved. Those units are now in Needs attention." : "Result saved.");
  }
}

// ---- Small pieces ----
function segbar(counts, label) {
  const total = counts.reduce((a, b) => a + b, 0);
  const parts = BAR_ORDER.filter((l) => counts[l] > 0).map((l) =>
    `<span style="flex:${counts[l]};background:var(--lv${l})" data-tip="${levelName(l)}: ${plural(counts[l], "topic")}"></span>`).join("");
  const summary = BAR_ORDER.filter((l) => counts[l] > 0).map((l) => `${levelName(l)} ${counts[l]}`).join(", ");
  return `<div class="segbar" role="img" aria-label="${esc(label)}: ${summary || "no topics"} of ${total}">${parts}</div>`;
}
const meter = (pct, label) => `<div class="meter" role="img" aria-label="${esc(label)}: ${pct}%"><i style="width:${pct}%"></i></div>`;
const studyButton = (t, text = "Study") =>
  `<button class="mini" data-study="${esc(t.id)}" data-key="st:${esc(t.id)}"${activeTopic() === t.id ? " disabled" : ""}>${activeTopic() === t.id ? "Studying…" : text}</button>`;

function practiceItem(e, keyPrefix) {
  const id = `${keyPrefix}-${e.id}`;
  const units = e.covers_all ? "Whole subject" : e.unit_names.join(", ");
  return `<li class="pe${e.done ? " done" : ""}">
    <input type="checkbox" id="${esc(id)}" data-practice="${esc(e.id)}" data-key="${esc(id)}"${e.done ? " checked" : ""}>
    <label for="${esc(id)}">
      <span class="pe-title">${esc(e.title)}${e.end_of_subject ? ' <span class="kind final">End of subject</span>' : ` <span class="kind">${KIND_LABEL[e.kind]}</span>`}</span>
      <small>${esc(e.school)} · ${esc(e.course)}</small>
      <small>${esc(units)}${e.note ? ` · ${esc(e.note)}` : ""}${e.done ? ` · <b>Done ${shortDate(e.done_on)}</b>` : ""}</small>
      ${e.done && resultText(e) ? `<small class="pe-result">${esc(resultText(e, unitNames()))}</small>` : ""}
    </label>
    <span class="pe-links"><a href="${esc(e.url)}" target="_blank" rel="noopener">Open exam</a>${e.solutions_url ? `<a href="${esc(e.solutions_url)}" target="_blank" rel="noopener">Solutions</a>` : ""}${e.done ? `<button class="linkbtn" data-paper-result="${esc(e.id)}" data-key="pr-${esc(keyPrefix)}-${esc(e.id)}">${resultText(e) ? "Edit result" : "Add result"}</button>` : ""}</span>
  </li>`;
}

// ---- Sections ----
function renderHead() {
  const s = data.subject;
  const m = data.summary;
  const color = laneColor(s);
  document.title = `${s.name} · Study App`;
  $("crumbName").textContent = s.short_name;
  const semesters = [1, 2, 3, 4].flatMap((y) => [1, 2].map((t) => `Year ${y} · Sem ${t}`));
  $("head").innerHTML = `
    <div class="eyebrow" style="--c:${color}">${esc(s.lane_name.toUpperCase())} · TIER ${s.tier + 1}${s.kind === "gap_filler" ? " · MIT GAP-FILLER" : ""}${s.mit_code ? ` · MIT ${esc(s.mit_code)}` : ""}</div>
    <div class="title-row"><span class="lvl" title="Level ${m.level} of 5"><small>LV</small><b>${m.level}</b></span><h1>${esc(s.name)}</h1></div>
    <p class="none">${m.next_level_at ? `${m.next_level_at - m.mastery_pct}% more topic mastery to reach level ${m.level + 1}` : "Top level reached"} · <a href="tree.html#${encodeURIComponent(s.id)}">Show in skill tree</a></p>
    <div class="head-edit" style="--c:${color}">
      <div class="seg status-seg" role="group" aria-label="Subject status">
        ${[["not_started", "Not started"], ["in_progress", "In progress"], ["done", "Done"]].map(([v, l]) =>
          `<button data-status="${v}" aria-pressed="${s.status === v}" data-key="st:${v}">${l}</button>`).join("")}
      </div>
      <label class="field">Semester<input id="f-semester" list="semesters" value="${esc(s.semester)}" placeholder="e.g. Year 1 · Sem 1" maxlength="30"></label>
      <datalist id="semesters">${semesters.map((x) => `<option value="${x}"></option>`).join("")}</datalist>
      <label class="field small">Grade<input id="f-grade" value="${esc(s.grade)}" placeholder="e.g. A" maxlength="10"></label>
      ${s.state === "locked" && s.status === "not_started" ? '<span class="none">Prerequisites not done yet</span>' : ""}
    </div>`;
}

function renderKpis() {
  const m = data.summary;
  const ex = m.next_exam;
  const studied = m.days_since_studied;
  $("kpis").innerHTML = `
    <div class="kpi"><span class="label">Topic mastery</span><span class="value">${m.mastery_pct}%</span>${segbar(m.level_counts, "Topics by mastery")}
      <span class="sub">${m.started} of ${m.topic_count} started · ${m.mastered} mastered${m.minutes_total ? ` · ${hoursAndMinutes(m.minutes_total)} studied` : ""}${studied == null ? "" : `, last ${ago(studied)}`}</span></div>
    <div class="kpi"><span class="label">Due for review</span><span class="value">${m.due_count}</span>
      ${m.due_count ? `<button class="btn primary kpi-btn" id="reviewDue">Review ${plural(m.due_count, "due topic")}</button>`
        : `<span class="sub">${data.upcoming_reviews[0] ? `Next: ${esc(data.upcoming_reviews[0].name)} ${inDays(data.upcoming_reviews[0].days_until_review)}` : "Nothing scheduled yet"}</span>`}</div>
    <div class="kpi"><span class="label">Next exam</span>${ex
      ? `<span class="value">${ex.days_left === 0 ? "Today" : `${ex.days_left}<small> days</small>`}</span><span class="sub">${esc(ex.name)} · ${ex.readiness_pct}% ready · past papers ${m.practice_done} of ${m.practice_total}</span>`
      : `<span class="value">–</span><span class="sub">No date set. <a href="#exams-section">Add one</a> · past papers ${m.practice_done} of ${m.practice_total}</span>`}</div>`;
}

function renderUnits() {
  $("levelLegend").innerHTML = BAR_ORDER.map((l) => `<span><i style="background:var(--lv${l})"></i>${levelName(l)}</span>`).join("");
  $("unitBars").innerHTML = data.units.map((u) => `<div class="unit-row">
      <div><a href="#u-${esc(u.id)}" data-unit-link>${esc(u.name)}</a><small>${u.topic_count - u.level_counts[0]} of ${u.topic_count} started</small></div>
      ${segbar(u.level_counts, u.name)}
      <span class="pct">${u.mastery_pct}%</span>
    </div>`).join("");
}



function renderPractice() {
  const exams = data.practice_exams;
  const m = data.summary;
  const scored = exams.filter((e) => e.done && e.score != null);
  const avg = scored.length ? Math.round(scored.reduce((a, e) => a + e.score, 0) / scored.length) : null;
  $("practiceSummary").textContent = exams.length ? `${m.practice_done} of ${exams.length} done${avg != null ? ` · average ${avg}%` : ""}` : "";
  if (!exams.length) {
    $("practice").innerHTML = `<p class="empty">No openly published past papers from top universities were found for this subject. Use your own course's past papers, and add them to topics as resources.</p>`;
    return;
  }
  const finals = exams.filter((e) => e.end_of_subject);
  const others = exams.filter((e) => !e.end_of_subject);
  const pct = Math.round((100 * m.practice_done) / exams.length);
  $("practice").innerHTML = `
    <div class="pe-progress">${meter(pct, "Past papers done")}<span>${pct}%</span></div>
    <div class="pe-cols">
      <div><h3>By unit</h3>${others.length ? `<ul class="pe-list">${others.map((e) => practiceItem(e, "pe")).join("")}</ul>` : '<p class="empty">Only end-of-subject exams for this subject.</p>'}</div>
      <div><h3>End-of-subject exams</h3>${finals.length ? `<ul class="pe-list">${finals.map((e) => practiceItem(e, "pe")).join("")}</ul>` : '<p class="empty">No final exams were found. The unit exams together cover the subject.</p>'}</div>
    </div>`;
}

function renderExams() {
  const exams = data.exams;
  const units = data.units;
  const soon = new Date(Date.parse(data.today) + 14 * 86400000).toISOString().slice(0, 10);
  $("toggleExamForm").setAttribute("aria-expanded", String(showExamForm));
  $("toggleExamForm").textContent = showExamForm ? "Cancel" : "Add exam date";
  $("exams").innerHTML = `
    ${showExamForm ? `<form class="form" data-form="exam">
      <div class="form-row"><label class="field">Name<input name="name" required maxlength="60" placeholder="e.g. Midterm" data-key="ex:name"></label>
        <label class="field">Date<input name="exam_date" type="date" required value="${soon}"></label></div>
      <fieldset><legend>Units it covers</legend>${units.map((u) =>
        `<label class="check"><input type="checkbox" name="unit" value="${esc(u.id)}" checked> ${esc(u.name)}</label>`).join("")}</fieldset>
      <button class="btn primary" type="submit">Save exam</button>
    </form>` : ""}
    ${exams.length ? `<ul class="exam-list">${exams.map((e) => `
      <li class="${e.past ? "past" : ""}">
        <div class="who"><b>${esc(e.name)}</b><small>${longDate(e.exam_date)} · ${e.past ? ago(-e.days_left) : inDays(e.days_left)} · ${e.unit_names.length === units.length ? "Whole subject" : esc(e.unit_names.join(", "))}</small></div>
        ${meter(e.readiness_pct, "Readiness")}<span class="pct">${e.readiness_pct}%</span>
        <button class="mini" data-del-exam="${e.id}" aria-label="Delete ${esc(e.name)}">Delete</button>
      </li>`).join("")}</ul>
      <p class="intervals">Readiness is the average mastery of the topics the exam covers.</p>`
      : showExamForm ? "" : '<p class="empty">No dates yet. Add your midterm and final to get a countdown and exam prep in your Today plan.</p>'}`;
}





function neighbourList(items, emptyText) {
  if (!items.length) return `<p class="empty">${emptyText}</p>`;
  return `<ul class="nb">${items.map((n) => `
    <li><a href="subject.html?id=${encodeURIComponent(n.id)}" class="${n.kind === "gap_filler" ? "gap" : ""}" style="--c:${laneColor(n)}"><i></i><span>${esc(n.short_name)}<small>${STATE_TEXT[n.state]}${n.kind === "gap_filler" ? " · MIT gap-filler" : ""}</small></span></a>
      ${meter(n.mastery_pct, "Topic mastery")}<span class="pct">${n.mastery_pct}%</span></li>`).join("")}</ul>`;
}

function renderLinks() {
  const courses = data.needs.filter((n) => n.kind === "course");
  const done = courses.filter((n) => n.state === "done").length;
  $("links").innerHTML = `<div class="links">
    <div><h3>Builds on</h3>
      ${courses.length ? `<p class="none" style="margin-bottom:8px">${done} of ${plural(courses.length, "prerequisite")} done. Bars show topic mastery.</p>` : ""}
      ${neighbourList(data.needs, "Nothing. This is a starting subject.")}</div>
    <div><h3>Leads to</h3>${neighbourList(data.unlocks, "Nothing further in your curriculum.")}</div>
  </div>`;
}

// ---- Topics ----
function topicMeta(t) {
  const bits = [];
  if (t.mastery === 0) bits.push("<span>Not studied yet</span>");
  else {
    bits.push(`<span>Reviewed ${ago(daysBetween(t.last_reviewed, data.today))}</span>`);
    bits.push(t.is_due ? '<span class="badge due">Due for review</span>' : `<span>Next review ${inDays(t.days_until_review)}</span>`);
  }
  if (t.on_next_exam) bits.push('<span class="kind exam">On next exam</span>');
  if (t.weak_reasons.length) bits.push(`<span class="badge attention">${esc(t.weak_reasons[0])}</span>`);
  const counts = [
    t.cards.length && plural(t.cards.length, "card"),
    t.practice_exam_ids.length && plural(t.practice_exam_ids.length, "past paper"),
    t.resources.length && plural(t.resources.length, "resource"),
    t.minutes && `${hoursAndMinutes(t.minutes)} studied`,
  ].filter(Boolean);
  if (counts.length) bits.push(`<span>${counts.join(" · ")}</span>`);
  return bits.join("");
}

function linkList(links, emptyText) {
  if (!links.length) return `<p class="empty">${emptyText}</p>`;
  return `<ul class="tlinks">${links.map((l) => `<li>
    <a href="subject.html?id=${encodeURIComponent(l.subject_id)}#t-${encodeURIComponent(l.topic_id)}">${esc(l.subject_name)} › ${esc(l.topic_name)}</a>
    <small>${esc(l.why)}</small></li>`).join("")}</ul>`;
}

function topicDetails(t) {
  const practice = t.practice_exam_ids.map(practiceById).filter(Boolean);
  return `<div class="details">
    <div class="dcol">
    <section>
      <h4>Notes</h4>
      <textarea data-notes aria-label="Notes for ${esc(t.name)}" data-key="ta:${esc(t.id)}" placeholder="Key formulas, worked examples, questions for class…">${esc(t.notes)}</textarea>
      <small class="none">Saved when you click outside the box.</small>
    </section>
    <section>
      <h4>Past papers on this topic</h4>
      ${practice.length ? `<ul class="pe-list compact">${practice.map((e) => practiceItem(e, "tp-" + t.id)).join("")}</ul>`
        : '<p class="empty">None of the past papers cover this unit.</p>'}
    </section>
    </div>
    <div class="dcol">
    <section>
      <h4>Flashcards <span class="none">${t.cards.length}</span></h4>
      ${t.cards.length ? `<ul class="cards">${t.cards.map((c) => `<li>
        <div><b>${esc(c.front)}</b><span>${esc(c.back)}</span><small>Box ${c.box} of 4</small></div>
        <button class="mini" data-del-card="${c.id}" aria-label="Delete card">Delete</button></li>`).join("")}</ul>
        <button class="mini" data-practise-topic="${esc(t.id)}">Practise ${plural(t.cards.length, "card")}</button>`
        : '<p class="empty">No cards yet. Practising cards sets this topic’s mastery for you.</p>'}
      <form class="form" data-form="card">
        <label class="field">Question<input name="front" required maxlength="500" data-key="cf:${esc(t.id)}"></label>
        <label class="field">Answer<textarea name="back" required maxlength="1500" rows="2"></textarea></label>
        <button class="mini" type="submit">Add card</button>
      </form>
    </section>
    <section>
      <h4>Resources</h4>
      ${t.resources.length ? `<ul class="res">${t.resources.map((r) => `<li>
        <span class="kind">${esc(RESOURCE_KINDS.find(([k]) => k === r.kind)?.[1] ?? r.kind)}</span>
        <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>
        <button class="mini" data-del-res="${r.id}" aria-label="Delete ${esc(r.title)}">Delete</button></li>`).join("")}</ul>` : ""}
      <form class="form" data-form="resource">
        <div class="form-row">
          <label class="field">Title<input name="title" required maxlength="120" placeholder="e.g. Strang lecture 29"></label>
          <label class="field">Type<select name="kind">${RESOURCE_KINDS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select></label>
        </div>
        <label class="field">Link<input name="url" type="url" required pattern="https?://.+" placeholder="https://"></label>
        <button class="mini" type="submit">Add resource</button>
      </form>
    </section>
    </div>
    <section class="wide">
      <h4>Connections to other subjects</h4>
      <div class="two">
        <div><h5>Builds on</h5>${linkList(t.links_in, "No earlier topics linked.")}</div>
        <div><h5>Used later in</h5>${linkList(t.links_out, "No later topics linked.")}</div>
      </div>
    </section>
  </div>`;
}

function renderTopics() {
  const topics = allTopics();
  const test = FILTERS.find(([key]) => key === filter)[2];
  $("filters").innerHTML = FILTERS.map(([key, label, fn]) =>
    `<button data-filter="${key}" aria-pressed="${filter === key}" data-key="f:${key}">${label} <span class="none">${topics.filter(fn).length}</span></button>`).join("");
  const cardCount = data.summary.card_count;
  $("practiseAll").textContent = cardCount ? `Practise ${plural(cardCount, "flashcard")}` : "Practise flashcards";
  $("practiseAll").disabled = !cardCount;

  const blocks = data.units.map((u) => {
    const shown = u.topics.filter(test);
    if (!shown.length) return "";
    return `<div class="unit-block" id="u-${esc(u.id)}">
      <div class="unit-head"><h3>${esc(u.name)}</h3><span>${u.mastery_pct}% · ${plural(u.topic_count, "topic")}</span></div>
      ${shown.map((t) => {
        const open = openDetails.has(t.id);
        return `<div class="topic" id="t-${esc(t.id)}" data-topic="${esc(t.id)}">
          <div><div class="name">${t.ai_key ? '<span class="star" title="Key topic for AI">★</span>' : ""}${esc(t.name)}</div>
            <div class="tmeta">${topicMeta(t)}</div></div>
          <div class="lv" role="group" aria-label="Mastery of ${esc(t.name)}">${data.mastery_labels.map((l, i) =>
            `<button data-level="${i}" aria-pressed="${t.mastery === i}" style="--lvc:var(--lv${i});--lvink:var(--lv${i}-ink)" data-key="lv:${esc(t.id)}:${i}">${l}</button>`).join("")}</div>
          <div class="acts">
            ${studyButton(t)}
            <button class="mini" data-act="details" aria-expanded="${open}" data-key="dt:${esc(t.id)}">Details</button>
          </div>
          ${open ? topicDetails(t) : ""}
        </div>`;
      }).join("")}
    </div>`;
  }).join("");
  $("topicList").innerHTML = blocks || '<p class="empty">No topics match this filter.</p>';
}

function renderJump() {
  $("jump").innerHTML = data.lanes.map((l) => {
    const opts = data.all_subjects.filter((s) => s.lane_id === l.id).map((s) =>
      `<option value="${s.id}"${s.id === subjectId ? " selected" : ""}>${esc(s.short_name)}${s.kind === "gap_filler" ? " (MIT gap)" : ""}</option>`).join("");
    return `<optgroup label="${esc(l.name)}">${opts}</optgroup>`;
  }).join("");
}

function render() {
  const key = document.activeElement?.dataset?.key;
  renderHead();
  renderKpis();
  renderUnits();
  renderPractice();
  renderExams();
  renderLinks();
  renderTopics();
  if (key) document.querySelector(`[data-key="${CSS.escape(key)}"]`)?.focus();
}

async function reload() {
  data = await fetchDashboard(subjectId);
  render();
}

// ---- Actions ----
async function run(action, success) {
  try {
    const res = await action();
    await reload();
    if (success) toast(typeof success === "function" ? success(res) : success);
    if (res?.subject_started) toast(`Marked ${data.subject.short_name} as in progress.`);
    return res;
  } catch (err) {
    toast(`Couldn't save: ${err.message}`, true);
    return null;
  }
}

function startStudy(topicId) {
  const t = topicById(topicId);
  if (startTimer({ topicId: t.id, topicName: t.name, subjectId, subjectName: data.subject.short_name })) renderTopics();
}

function practise(topicId) {
  const t = topicId ? topicById(topicId) : null;
  openPractice({
    subjectId, topicId, labels: data.mastery_labels,
    title: t ? t.name : `${data.subject.short_name} flashcards`,
  }, () => reload());
}

async function saveSubject(changes) {
  const s = data.subject;
  const body = { status: s.status, semester: s.semester, grade: s.grade, ...changes };
  try {
    const res = await saveProgress(subjectId, body);
    await reload();
    if (res.unlocked.length) toast(`Unlocked ${plural(res.unlocked.length, "subject")} on the skill tree.`);
    else toast("Saved.");
  } catch (err) {
    toast(`Couldn't save: ${err.message}`, true);
  }
}

function reviewDue() {
  openReview(subjectId, () => reload());
}

document.addEventListener("click", (e) => {
  const el = (sel) => e.target.closest(sel);
  const topicEl = el("[data-topic]");
  if (el("[data-status]")) { saveSubject({ status: el("[data-status]").dataset.status }); return; }
  if (el("#reviewDue")) { reviewDue(); return; }
  if (el("[data-paper-result]")) { askPaperResult(practiceById(el("[data-paper-result]").dataset.paperResult)); return; }

  if (el("[data-level]") && topicEl) { run(() => updateTopic(topicEl.dataset.topic, { mastery: Number(el("[data-level]").dataset.level) })); return; }
  if (el("[data-study]")) { startStudy(el("[data-study]").dataset.study); return; }
  if (el("[data-practise-topic]")) { practise(el("[data-practise-topic]").dataset.practiseTopic); return; }
  if (el("[data-del-card]")) { run(() => deleteCard(el("[data-del-card]").dataset.delCard), "Card deleted."); return; }
  if (el("[data-del-res]")) { run(() => deleteResource(el("[data-del-res]").dataset.delRes), "Resource removed."); return; }
  if (el("[data-del-exam]")) { run(() => deleteExam(el("[data-del-exam]").dataset.delExam), "Exam deleted."); return; }

  const act = el("[data-act]");
  if (act && topicEl) {
    const id = topicEl.dataset.topic;
    if (act.dataset.act === "details") {
      if (openDetails.has(id)) openDetails.delete(id); else openDetails.add(id);
      renderTopics();
      document.querySelector(`[data-key="${CSS.escape(`dt:${id}`)}"]`)?.focus();
    }
    return;
  }
  const f = el("[data-filter]");
  if (f) { filter = f.dataset.filter; renderTopics(); document.querySelector(`[data-key="f:${filter}"]`)?.focus(); return; }
  if (el("[data-unit-link]") && filter !== "all") { filter = "all"; renderTopics(); }
});

document.addEventListener("change", (e) => {
  if (e.target.id === "f-semester") { saveSubject({ semester: e.target.value }); return; }
  if (e.target.id === "f-grade") { saveSubject({ grade: e.target.value }); return; }
  if (e.target.matches("textarea[data-notes]")) {
    run(() => updateTopic(e.target.closest("[data-topic]").dataset.topic, { notes: e.target.value }));
  }
  if (e.target.matches("input[data-practice]")) {
    const done = e.target.checked;
    const exam = practiceById(e.target.dataset.practice);
    run(() => tickPracticeExam(exam.id, done), done ? `Ticked off: ${exam.title}` : `Unticked: ${exam.title}`)
      .then((res) => { if (res && done) askPaperResult(practiceById(exam.id) || exam); });
  }
});

document.addEventListener("submit", (e) => {
  const form = e.target.closest("form[data-form]");
  if (!form) return;
  e.preventDefault();
  const fd = new FormData(form);
  const kind = form.dataset.form;
  if (kind === "exam") {
    const unitIds = fd.getAll("unit");
    if (!unitIds.length) { toast("Pick at least one unit the exam covers.", true); return; }
    run(() => addExam(subjectId, { name: fd.get("name"), exam_date: fd.get("exam_date"), unit_ids: unitIds }), "Exam date added.")
      .then((res) => { if (res) { showExamForm = false; renderExams(); } });
    return;
  }
  const topicId = form.closest("[data-topic]").dataset.topic;
  if (kind === "card") run(() => addCard(topicId, { front: fd.get("front"), back: fd.get("back") }), "Card added.");
  if (kind === "resource") run(() => addResource(topicId, { title: fd.get("title"), url: fd.get("url"), kind: fd.get("kind") }), "Resource added.");
});

$("toggleExamForm").addEventListener("click", () => {
  showExamForm = !showExamForm;
  renderExams();
  if (showExamForm) document.querySelector('[data-key="ex:name"]')?.focus();
});
$("practiseAll").addEventListener("click", () => practise(null));
$("jump").addEventListener("change", (e) => { location.href = `subject.html?id=${encodeURIComponent(e.target.value)}`; });

// Tooltip for chart marks
const tip = $("tip");
function showTip(el) {
  const r = el.getBoundingClientRect();
  tip.textContent = el.dataset.tip;
  tip.style.left = `${Math.min(Math.max(r.left + r.width / 2, 90), window.innerWidth - 90)}px`;
  tip.style.top = `${r.top}px`;
  tip.hidden = false;
}
document.addEventListener("mouseover", (e) => { const el = e.target.closest("[data-tip]"); if (el) showTip(el); else tip.hidden = true; });
document.addEventListener("focusin", (e) => { const el = e.target.closest("[data-tip]"); if (el) showTip(el); else tip.hidden = true; });
window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });

// Jumping to a topic from another subject: open it and scroll to it.
function openFromHash() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (hash.startsWith("t-") && topicById(hash.slice(2))) {
    filter = "all";
    openDetails.add(hash.slice(2));
    renderTopics();
    const el = document.getElementById(hash);
    el?.scrollIntoView({ block: "start" });
    el?.classList.add("flash");
  } else if (hash) {
    document.getElementById(hash)?.scrollIntoView();
  }
}

// ---- Start ----
initNav("subject");
if (!FILTERS.some(([key]) => key === filter)) filter = "all";
initTimer((session) => { if (session.subjectId === subjectId) reload(); });
(async function start() {
  try {
    data = await fetchDashboard(subjectId);
    renderJump();
    render();
    openFromHash();
    if (params.get("review") === "1" && data.summary.due_count) reviewDue();
  } catch (err) {
    $("head").innerHTML = `<h1>Couldn't load this subject</h1><p class="none">${esc(err.message)}. <a href="tree.html">Back to the skill tree</a></p>`;
  }
})();
window.addEventListener("hashchange", openFromHash);
window.addEventListener("timerchange", () => { if (data) renderTopics(); });
