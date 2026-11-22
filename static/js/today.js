// Today: the home page. A short plan picked from what's due, your exams and practice exams.
import { addToPlan, fetchToday, rebuildPlan, tickPlanItem, saveSettings } from "./api.js";
import { initNav } from "./nav.js";
import { openPractice } from "./practice.js";
import { openReview } from "./review.js";
import { activeTopic, initTimer, startTimer } from "./timer.js";
import { esc, hoursAndMinutes, inDays, longDate, plural, toast } from "./util.js";

const MASTERY_LABELS = ["Not started", "Learning", "Practising", "Confident", "Mastered"];
const KIND_LABEL = {
  review: "Review", exam_prep: "Exam prep", practice: "Past paper", cards: "Flashcards",
  attention: "Needs attention", new: "New topic",
};
const TIMED = new Set(["exam_prep", "attention", "new"]);

let data = null;
const $ = (id) => document.getElementById(id);
const subjectUrl = (i) => `subject.html?id=${encodeURIComponent(i.subject_id)}`;

function actionsFor(i, primary) {
  const cls = primary ? "btn hero-btn" : "btn";
  if (TIMED.has(i.kind)) {
    const busy = activeTopic() === i.topic_id;
    const link = i.kind === "review" ? `${subjectUrl(i)}&filter=due` : `${subjectUrl(i)}#t-${encodeURIComponent(i.topic_id)}`;
    return `<button class="${cls}" data-start="${esc(i.key)}"${busy ? " disabled" : ""}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4l13 8-13 8z"></path></svg>${busy ? "Studying…" : `Start ${i.minutes} min`}</button>
      <a class="sub-link" href="${link}">Open</a>`;
  }
  if (i.kind === "practice") {
    return `<a class="${cls}" href="${esc(i.url)}" target="_blank" rel="noopener">Open exam</a>
      ${i.solutions_url ? `<a class="sub-link" href="${esc(i.solutions_url)}" target="_blank" rel="noopener">Solutions</a>` : ""}`;
  }
  if (i.kind === "cards") return `<button class="${cls}" data-cards="${esc(i.key)}">Practise</button>`;
  if (i.kind === "review") {
    return `<button class="${cls}" data-review-subject="${esc(i.subject_id)}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4l13 8-13 8z"></path></svg>Start review</button>
      <a class="sub-link" href="${subjectUrl(i)}&filter=due">Open</a>`;
  }
  return "";
}

const BUDGETS = [30, 45, 60, 90, 120, 180, 240];

function renderBudget() {
  const current = data.daily_minutes;
  const options = [...new Set([...BUDGETS, ...(current ? [current] : [])])].sort((a, b) => a - b);
  $("budget").innerHTML = `<option value="">No limit</option>` +
    options.map((m) => `<option value="${m}"${m === current ? " selected" : ""}>${hoursAndMinutes(m)}</option>`).join("");
}

function renderHead() {
  renderBudget();
  $("tDate").textContent = longDate(data.today).toUpperCase();
  const open = data.plan.filter((i) => !i.done);
  $("tTitle").textContent = open.length ? `Today · ${hoursAndMinutes(data.planned_minutes)}` : "Today · plan done";
  const exam = data.upcoming_exams[0];
  const parts = [];
  if (data.studied_today_minutes) parts.push(`${hoursAndMinutes(data.studied_today_minutes)} studied so far today.`);
  parts.push(exam ? `${exam.name} in ${exam.subject_name} is ${inDays(exam.days_left)}, ${exam.readiness_pct}% ready.`
    : "No exam dates yet. Add them on a subject page to get exam prep in this plan.");
  $("tSub").textContent = parts.join(" ");
  const s = data.streak_days;
  $("tStreak").innerHTML = s
    ? `<span class="streak" title="Days in a row with any study">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-3 2-4 2-6 2 1 3 2 3 4"></path></svg>
        ${s}-day streak${data.studied_today ? "" : " · study today to keep it"}</span>`
    : `<span class="streak cold">No streak yet. Finish one item to start one.</span>`;
}

function renderPlan() {
  const open = data.plan.filter((i) => !i.done);
  const done = data.plan.filter((i) => i.done);
  const [next, ...rest] = open;
  $("upNext").innerHTML = next ? `
    <article class="hero" aria-label="Up next">
      <div class="hero-text">
        <span class="hero-label">Up next · ${KIND_LABEL[next.kind]} · ${next.minutes} min</span>
        <span class="hero-title">${esc(next.title)}</span>
        <span class="hero-detail">${esc(next.subject_name)} · ${esc(next.detail)}</span>
      </div>
      <div class="hero-actions">
        ${actionsFor(next, true)}
        <label class="hero-tick"><input type="checkbox" data-tick="${esc(next.key)}"> ${next.kind === "practice" ? "Mark paper done" : "Mark done"}</label>
      </div>
    </article>` : `<article class="hero calm"><span class="hero-title">Nothing left in today's plan.</span>
      <span class="hero-detail">Good work. Add more if you want to keep going.</span>
      <div class="hero-actions"><button class="btn" data-more>Add more to today</button></div></article>`;
  $("planTools").innerHTML = next ? `<button class="linkbtn" data-more>Add more to today's plan</button>
    <button class="linkbtn" data-rebuild title="Keeps what you've done and picks the rest again">Rebuild plan</button>` : "";

  $("thenHead").hidden = !rest.length;
  $("plan").innerHTML = rest.map((i) => `
    <li class="item">
      <input type="checkbox" id="tick-${esc(i.key)}" data-tick="${esc(i.key)}">
      <label for="tick-${esc(i.key)}" class="item-text">
        <span class="item-title">${esc(i.title)}</span>
        <small><span class="kind-tag">${KIND_LABEL[i.kind]}</span> ${esc(i.subject_name)} · ${esc(i.detail)}</small>
      </label>
      <span class="item-min">${i.minutes} min</span>
      <span class="item-actions">${actionsFor(i, false)}</span>
    </li>`).join("");

  const doneRows = done.map((i) => `
    <li class="item">
      <input type="checkbox" id="tick-${esc(i.key)}" data-tick="${esc(i.key)}" checked${i.done_by === "action" && i.kind !== "practice" ? ' disabled title="Done through the real activity"' : ""}>
      <label for="tick-${esc(i.key)}" class="item-text"><span class="item-title">${esc(i.title)}</span><small>${esc(i.subject_name)}</small></label>
      <span class="item-min">${i.minutes} min</span>
    </li>`).concat(data.sessions_today.map((s) => `
    <li class="item session"><span class="dot" aria-hidden="true"></span>
      <span class="item-text"><span class="item-title">Studied ${esc(s.topic_name)}</span><small>Timed session</small></span>
      <span class="item-min">${s.minutes} min</span></li>`));
  $("doneHead").hidden = !doneRows.length;
  $("done").innerHTML = doneRows.join("");
}

function renderSide() {
  const exams = data.upcoming_exams;
  $("exams").innerHTML = exams.length ? `<ul class="side-list">${exams.map((e) => `
    <li><span class="days"><b>${e.days_left}</b><small>${e.days_left === 1 ? "day" : "days"}</small></span>
      <span><a href="subject.html?id=${encodeURIComponent(e.subject_id)}">${esc(e.name)} · ${esc(e.subject_name)}</a><br>
      <small class="none">${e.readiness_pct}% ready · ${plural(e.topic_count, "topic")}</small></span></li>`).join("")}</ul>`
    : '<p class="empty">No upcoming exams. Add dates on a subject page under “Your exam dates”.</p>';

  const week = data.week;
  const total = week.reduce((a, d) => a + d.minutes, 0);
  const max = Math.max(60, ...week.map((d) => d.minutes));
  $("weekTotal").textContent = hoursAndMinutes(total);
  const days = ["M", "T", "W", "T", "F", "S", "S"];
  $("week").innerHTML = `<div class="week" role="img" aria-label="Minutes studied per day this week: ${week.map((d, i) => `${days[i]} ${d.minutes}`).join(", ")}">
    ${week.map((d, i) => `<span class="wday${d.is_today ? " today" : ""}${d.is_future ? " future" : ""}">
      <span class="wbar"><i style="height:${d.minutes ? Math.max(4, (100 * d.minutes) / max) : 0}%"></i></span>
      <small>${days[i]}</small></span>`).join("")}
  </div>`;

  $("subjects").innerHTML = data.subjects.length ? `<ul class="side-list">${data.subjects.map((s) => `
    <li><span class="lvl" title="Level ${s.level} of 5"><small>LV</small><b>${s.level}</b></span>
      <span class="subj"><a href="subject.html?id=${encodeURIComponent(s.id)}">${esc(s.short_name)}</a>
        <span class="mini-bar" role="img" aria-label="${s.mastery_pct}% topic mastery"><i style="width:${s.mastery_pct}%;background:var(--${s.lane_id})"></i></span>
        <small class="none">${s.mastery_pct}%${s.next_level_at ? ` · ${s.next_level_at - s.mastery_pct}% to level ${s.level + 1}` : " · top level"}</small></span></li>`).join("")}</ul>
      <p class="none">Past papers done: ${data.practice_done} of ${data.practice_total}</p>`
    : '<p class="empty">No subjects in progress. Start one from your plan, or mark one as in progress on the skill tree.</p>';

  $("weak").innerHTML = data.weak_spots.length ? `<ul class="side-list plain">${data.weak_spots.slice(0, 4).map((t) => `
    <li><span><a href="subject.html?id=${encodeURIComponent(t.subject_id)}#t-${encodeURIComponent(t.id)}">${esc(t.name)}</a><br>
      <small class="none">${esc(t.subject_name)} · ${esc(t.weak_reasons.join(", "))}</small></span></li>`).join("")}</ul>`
    : '<p class="empty">Nothing needs attention.</p>';
}

function render() {
  renderHead();
  renderPlan();
  renderSide();
}

async function reload() {
  try {
    data = await fetchToday();
    render();
  } catch (err) {
    $("tSub").textContent = `Couldn't load today's plan: ${err.message}. Check that the server is running.`;
  }
}

const itemByKey = (key) => data.plan.find((i) => i.key === key);

document.addEventListener("change", async (e) => {
  const key = e.target.dataset?.tick;
  if (!key) return;
  try {
    await tickPlanItem(key, e.target.checked);
    await reload();
    if (e.target.checked) toast(itemByKey(key)?.kind === "practice" ? "Past paper ticked off." : "Done. Nice work.");
  } catch (err) {
    toast(`Couldn't save: ${err.message}`, true);
  }
});

$("budget").addEventListener("change", async (e) => {
  const minutes = e.target.value ? Number(e.target.value) : null;
  try {
    await saveSettings({ daily_minutes: minutes });
    await reload();
    toast(minutes ? `Plan fitted to ${hoursAndMinutes(minutes)}. Finished items were kept.` : "No time limit. Plan rebuilt.");
  } catch (err) {
    toast(`Couldn't save: ${err.message}`, true);
  }
});

async function planAction(fn, message) {
  try {
    const res = await fn();
    await reload();
    if (res && res.added === 0) toast("Nothing more to add right now.");
    else if (message) toast(message);
  } catch (err) {
    toast(`Couldn't update the plan: ${err.message}`, true);
  }
}

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-more]")) { planAction(addToPlan, "Added to today's plan."); return; }
  if (e.target.closest("[data-rebuild]")) { planAction(rebuildPlan, "Plan rebuilt. Finished items were kept."); return; }
  const start = e.target.closest("[data-start]");
  if (start) {
    const i = itemByKey(start.dataset.start);
    startTimer({ topicId: i.topic_id, topicName: i.topic_name, subjectId: i.subject_id, subjectName: i.subject_name, minutes: i.minutes });
    return;
  }
  const rv = e.target.closest("[data-review-subject]");
  if (rv) { openReview(rv.dataset.reviewSubject, () => reload()); return; }
  const cards = e.target.closest("[data-cards]");
  if (cards) {
    const i = itemByKey(cards.dataset.cards);
    openPractice({ subjectId: i.subject_id, title: `${i.subject_name} flashcards`, labels: MASTERY_LABELS }, () => reload());
  }
});

window.addEventListener("timerchange", () => { if (data) renderPlan(); });
initNav("today");
initTimer(() => reload());
reload();
