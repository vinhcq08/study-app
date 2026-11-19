// Pomodoro study timer. One session at a time; it survives page reloads and follows you
// between pages. Starting a session opens focus mode, a calm full-screen view of the timer.
// When the time is up, the minutes are logged to the topic.
import { logSession } from "./api.js";
import { esc, toast } from "./util.js";

const KEY = "study-timer-v1";
const LENGTHS = [15, 25, 50];

let state = null;   // { topicId, topicName, subjectId, subjectName, minutes, elapsedMs, runningSince }
let bar = null;
let focus = null;
let focusOpen = false;
let onLogged = () => {};
let audio = null;
let lastFocused = null;
const baseTitle = document.title;

function load() {
  try { state = JSON.parse(localStorage.getItem(KEY)) || null; } catch { state = null; }
}
function save() {
  try { state ? localStorage.setItem(KEY, JSON.stringify(state)) : localStorage.removeItem(KEY); } catch { /* storage blocked */ }
}
const elapsed = () => state.elapsedMs + (state.runningSince ? Date.now() - state.runningSince : 0);
const fmt = (ms) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};
const snap = (min) => LENGTHS.reduce((best, m) => (Math.abs(m - min) < Math.abs(best - min) ? m : best), 25);

function render() {
  window.dispatchEvent(new CustomEvent("timerchange"));
  if (!state) {
    bar.hidden = true;
    closeFocus();
    document.title = baseTitle;
    return;
  }
  const running = !!state.runningSince;
  bar.hidden = focusOpen;
  bar.innerHTML = `
    <div class="timer-info"><span class="timer-label">${running ? "Studying" : "Paused"}</span>
      <b>${esc(state.topicName)}</b><small>${esc(state.subjectName)}</small></div>
    <span class="timer-clock" data-clock></span>
    <label class="sr-only" for="timer-len">Session length</label>
    <select id="timer-len" data-timer="length">${LENGTHS.map((m) => `<option value="${m}"${m === state.minutes ? " selected" : ""}>${m} min</option>`).join("")}</select>
    <button class="btn" data-timer="focus">Focus mode</button>
    <button class="btn" data-timer="toggle">${running ? "Pause" : "Resume"}</button>
    <button class="btn" data-timer="finish">Finish and log</button>
    <button class="btn" data-timer="discard">Discard</button>`;
  focus.innerHTML = `
    <span class="f-label">${running ? "Focus session" : "Paused"} · ${esc(state.subjectName)}</span>
    <span class="f-topic" id="focus-title">${esc(state.topicName)}</span>
    <span class="f-clock" data-fclock aria-live="off"></span>
    <div class="f-ring" role="img" aria-label="Session progress"><i data-fring></i></div>
    <div class="f-actions">
      <button class="main" data-timer="toggle">${running ? "Pause" : "Resume"}</button>
      <button data-timer="finish">Finish and log</button>
      <button data-timer="unfocus">Leave focus mode</button>
    </div>`;
  focus.hidden = !focusOpen;
  tick();
}

function tick() {
  if (!state) return;
  const total = state.minutes * 60000;
  const left = total - elapsed();
  if (left <= 0) { finish(true); return; }
  const clock = bar.querySelector("[data-clock]");
  if (clock) clock.textContent = fmt(left);
  const fclock = focus.querySelector("[data-fclock]");
  if (fclock) fclock.textContent = fmt(left);
  const ring = focus.querySelector("[data-fring]");
  if (ring) ring.style.width = `${Math.min(100, (100 * elapsed()) / total)}%`;
  document.title = `${fmt(left)} · ${baseTitle}`;
}

function openFocus() {
  if (!state) return;
  lastFocused = document.activeElement;
  focusOpen = true;
  render();
  focus.querySelector(".main")?.focus();
}

function closeFocus() {
  if (!focusOpen) return;
  focusOpen = false;
  if (focus) focus.hidden = true;
  if (bar && state) bar.hidden = false;
  if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
}

function chime() {
  if (!audio) return;
  try {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = 660;
    gain.gain.setValueAtTime(0.12, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 1.6);
    osc.connect(gain).connect(audio.destination);
    osc.start();
    osc.stop(audio.currentTime + 1.6);
  } catch { /* sound is optional */ }
}

async function finish(completed) {
  const session = state;
  const minutes = completed ? session.minutes : Math.floor(elapsed() / 60000);
  state = null;
  focusOpen = false;
  save();
  render();
  if (minutes < 1) { toast("Less than a minute, so nothing was logged."); return; }
  try {
    await logSession(session.topicId, minutes);
    if (completed) chime();
    toast(`${completed ? "Session complete. " : ""}Logged ${minutes} min on ${session.topicName}.`);
    onLogged(session);
  } catch (err) {
    toast(`Couldn't log the session: ${err.message}`, true);
  }
}

function onAction(e) {
  const action = e.target.closest("[data-timer]")?.dataset.timer;
  if (!state || !action || action === "length") return;
  if (action === "toggle") {
    if (state.runningSince) { state.elapsedMs = elapsed(); state.runningSince = null; }
    else state.runningSince = Date.now();
    save(); render();
  }
  if (action === "focus") openFocus();
  if (action === "unfocus") closeFocus();
  if (action === "finish") finish(false);
  if (action === "discard") { state = null; save(); render(); toast("Session discarded."); }
}

export function initTimer(callback) {
  if (callback) onLogged = callback;
  bar = Object.assign(document.createElement("div"), { className: "timer", hidden: true });
  bar.setAttribute("role", "region");
  bar.setAttribute("aria-label", "Study timer");
  focus = Object.assign(document.createElement("div"), { className: "focus", hidden: true });
  focus.setAttribute("role", "dialog");
  focus.setAttribute("aria-modal", "true");
  focus.setAttribute("aria-labelledby", "focus-title");
  document.body.append(bar, focus);
  load();
  render();
  setInterval(tick, 500);

  bar.addEventListener("click", onAction);
  focus.addEventListener("click", onAction);
  focus.addEventListener("keydown", (e) => { if (e.key === "Escape") closeFocus(); });
  bar.addEventListener("change", (e) => {
    if (e.target.dataset.timer === "length" && state) { state.minutes = Number(e.target.value); save(); tick(); }
  });
  window.addEventListener("storage", (e) => { if (e.key === KEY) { load(); render(); } });
}

export function startTimer({ topicId, topicName, subjectId, subjectName, minutes = 25 }) {
  if (state) {
    toast(`Finish or discard your session on ${state.topicName} first.`);
    return false;
  }
  try { audio = audio || new AudioContext(); } catch { audio = null; }
  state = { topicId, topicName, subjectId, subjectName, minutes: snap(minutes), elapsedMs: 0, runningSince: Date.now() };
  save();
  openFocus();
  return true;
}

export const activeTopic = () => state?.topicId ?? null;
