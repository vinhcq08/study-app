// Review session: steps through a subject's due topics one at a time.
// For each, you recall what you know, then say how well you know it now.
// That one answer sets the topic's mastery and restarts its review clock.
import { fetchReview, updateTopic } from "./api.js";
import { esc, plural, toast } from "./util.js";

const CHOICES = [1, 2, 3, 4];   // Learning … Mastered (keys 1 to 4)

let dialog = null;
let session = null;

function ensureDialog() {
  if (dialog) return;
  dialog = document.createElement("dialog");
  dialog.className = "practice review";
  dialog.setAttribute("aria-label", "Review session");
  document.body.append(dialog);
  dialog.addEventListener("click", onClick);
  dialog.addEventListener("keydown", onKey);
  dialog.addEventListener("close", () => {
    const s = session;
    session = null;
    if (s && s.answered > 0) s.onDone();
  });
}

function render() {
  const s = session;
  const labels = s.labels;
  if (s.index >= s.topics.length) {
    const changes = s.results.filter((r) => r.after !== r.before);
    dialog.innerHTML = `
      <div class="pc-head"><h2>Review · ${esc(s.subjectName)}</h2><button class="btn" data-rv="close">Close</button></div>
      <div class="pc-done">
        <p class="pc-big">Reviewed ${plural(s.answered, "topic")}${s.skipped ? `, skipped ${s.skipped}` : ""}</p>
        ${changes.length ? `<h3>Mastery changed</h3><ul class="pc-changes">${changes.map((r) =>
          `<li>${esc(r.name)}: ${labels[r.before]} → <b>${labels[r.after]}</b></li>`).join("")}</ul>`
          : '<p class="none">Every topic kept its level. Each one comes due again later.</p>'}
      </div>`;
    dialog.querySelector('[data-rv="close"]').focus();
    return;
  }
  const t = s.topics[s.index];
  dialog.innerHTML = `
    <div class="pc-head"><h2>Review · ${esc(s.subjectName)}</h2><span class="none">Topic ${s.index + 1} of ${s.topics.length}</span><button class="btn" data-rv="close">Close</button></div>
    <div class="pc-card">
      <span class="pc-topic">${esc(t.unit_name)} · ${t.days_overdue > 0 ? `due ${plural(t.days_overdue, "day")} ago` : "due today"} · now ${labels[t.mastery]}</span>
      <p class="pc-front">${esc(t.name)}</p>
      ${t.notes ? `<div class="rv-notes"><span class="pc-topic">Your notes</span><p>${esc(t.notes)}</p></div>`
        : '<p class="none">Explain the main ideas to yourself, or work one example, before you answer.</p>'}
    </div>
    <p class="rv-q">How well do you know it now?</p>
    <div class="rv-levels" role="group" aria-label="How well do you know it now?">
      ${CHOICES.map((l, i) => `<button class="pc-grade${l === t.mastery ? " same" : ""}" data-level="${l}"><b>${i + 1} · ${labels[l]}</b>${l === t.mastery ? "<small>Same as before</small>" : ""}</button>`).join("")}
    </div>
    <div class="rv-foot"><button class="linkbtn" data-rv="skip">Skip this topic</button><span class="pc-keys">Keys 1 to 4 answer, S skips.</span></div>`;
  dialog.querySelector(".pc-grade")?.focus();
}

async function answer(level) {
  const s = session;
  if (!s || s.busy || s.index >= s.topics.length) return;
  s.busy = true;
  const t = s.topics[s.index];
  try {
    await updateTopic(t.id, { mastery: level, reviewed: true });
    s.results.push({ name: t.name, before: t.mastery, after: level });
    s.answered += 1;
    s.index += 1;
  } catch (err) {
    toast(`Couldn't save that answer: ${err.message}`, true);
  }
  s.busy = false;
  render();
}

function skip() {
  session.skipped += 1;
  session.index += 1;
  render();
}

function onClick(e) {
  const action = e.target.closest("[data-rv]")?.dataset.rv;
  if (action === "close") dialog.close();
  if (action === "skip") skip();
  const lvl = e.target.closest("[data-level]");
  if (lvl) answer(Number(lvl.dataset.level));
}

function onKey(e) {
  if (!session || session.index >= session.topics.length) return;
  if (["1", "2", "3", "4"].includes(e.key)) { e.preventDefault(); answer(CHOICES[Number(e.key) - 1]); }
  if (e.key === "s" || e.key === "S") { e.preventDefault(); skip(); }
}

export async function openReview(subjectId, onDone) {
  let data;
  try {
    data = await fetchReview(subjectId);
  } catch (err) {
    toast(`Couldn't load the review: ${err.message}`, true);
    return;
  }
  if (!data.topics.length) { toast("Nothing is due for review in this subject."); onDone?.(); return; }
  ensureDialog();
  session = {
    topics: data.topics, labels: data.labels, subjectName: data.subject_name,
    onDone: onDone || (() => {}), index: 0, answered: 0, skipped: 0, results: [], busy: false,
  };
  render();
  dialog.showModal();
}
