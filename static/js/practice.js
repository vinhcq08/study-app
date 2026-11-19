// Flashcard practice in a dialog. Each answer moves the card between boxes,
// and the topic's mastery follows the average box.
import { fetchPractice, reviewCard } from "./api.js";
import { esc, plural, toast } from "./util.js";

const GRADES = [
  ["again", "Again", "Missed it. Back to box 1"],
  ["hard", "Hard", "Got it with effort. Stays put"],
  ["good", "Good", "Knew it. Up one box"],
  ["easy", "Easy", "Instant. Up two boxes"],
];

let dialog = null;
let session = null;

function ensureDialog() {
  if (dialog) return;
  dialog = document.createElement("dialog");
  dialog.className = "practice";
  dialog.setAttribute("aria-label", "Flashcard practice");
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
  if (s.index >= s.cards.length) {
    const counts = GRADES.map(([key, label]) => `${label} ${s.counts[key]}`).join(" · ");
    const changes = Object.values(s.changes).filter((c) => c.before !== c.after);
    dialog.innerHTML = `
      <div class="pc-head"><h2>${esc(s.title)}</h2><button class="btn" data-pc="close">Close</button></div>
      <div class="pc-done">
        <p class="pc-big">Practised ${plural(s.answered, "card")}</p>
        <p class="none">${counts}</p>
        ${changes.length ? `<h3>Mastery updated</h3><ul class="pc-changes">${changes.map((c) =>
          `<li>${esc(c.name)}: ${s.labels[c.before]} → <b>${s.labels[c.after]}</b></li>`).join("")}</ul>`
          : '<p class="none">Topic mastery didn’t change.</p>'}
      </div>`;
    dialog.querySelector('[data-pc="close"]').focus();
    return;
  }
  const card = s.cards[s.index];
  dialog.innerHTML = `
    <div class="pc-head"><h2>${esc(s.title)}</h2><span class="none">Card ${s.index + 1} of ${s.cards.length}</span><button class="btn" data-pc="close">Close</button></div>
    <div class="pc-card">
      <span class="pc-topic">${esc(card.topic_name)} · box ${card.box}</span>
      <p class="pc-front">${esc(card.front)}</p>
      ${s.revealed ? `<p class="pc-back">${esc(card.back)}</p>` : ""}
    </div>
    ${s.revealed
      ? `<div class="pc-grades">${GRADES.map(([key, label, hint], i) =>
          `<button class="pc-grade" data-grade="${key}"><b>${i + 1} · ${label}</b><small>${hint}</small></button>`).join("")}</div>`
      : `<button class="btn primary pc-reveal" data-pc="reveal">Show answer</button>`}
    <p class="pc-keys">Space shows the answer. Keys 1 to 4 grade it.</p>`;
  (dialog.querySelector(".pc-reveal") || dialog.querySelector(".pc-grade"))?.focus();
}

async function grade(result) {
  const s = session;
  if (!s || !s.revealed || s.busy) return;
  s.busy = true;
  const card = s.cards[s.index];
  try {
    const res = await reviewCard(card.id, result);
    s.counts[result] += 1;
    s.answered += 1;
    const change = s.changes[res.topic_id] || { name: card.topic_name, before: res.mastery_before, after: res.mastery };
    change.after = res.mastery;
    s.changes[res.topic_id] = change;
    s.index += 1;
    s.revealed = false;
  } catch (err) {
    toast(`Couldn't save that answer: ${err.message}`, true);
  }
  s.busy = false;
  render();
}

function onClick(e) {
  const action = e.target.closest("[data-pc]")?.dataset.pc;
  if (action === "close") dialog.close();
  if (action === "reveal") { session.revealed = true; render(); }
  const g = e.target.closest("[data-grade]");
  if (g) grade(g.dataset.grade);
}

function onKey(e) {
  if (!session || e.target.tagName === "SELECT") return;
  if ((e.key === " " || e.key === "Enter") && !session.revealed && session.index < session.cards.length) {
    e.preventDefault();
    session.revealed = true;
    render();
  } else if (["1", "2", "3", "4"].includes(e.key) && session.revealed) {
    e.preventDefault();
    grade(GRADES[Number(e.key) - 1][0]);
  }
}

export async function openPractice({ subjectId, topicId = null, title, labels }, onDone) {
  let cards;
  try {
    ({ cards } = await fetchPractice(subjectId, topicId));
  } catch (err) {
    toast(`Couldn't load flashcards: ${err.message}`, true);
    return;
  }
  if (!cards.length) { toast("No flashcards yet. Add some in a topic's details."); return; }
  ensureDialog();
  session = {
    cards, title, labels, onDone, index: 0, revealed: false, answered: 0, busy: false,
    counts: { again: 0, hard: 0, good: 0, easy: 0 }, changes: {},
  };
  render();
  dialog.showModal();
}
