// Small wrapper around the backend's JSON API.

import { BACKEND } from "./config.js";

// On the GitHub Pages site, Python runs once in the shell page (index.html) that shows this
// page in a frame. Opened on its own, a page goes through the shell instead.
function findShell() {
  try {
    if (window.parent !== window && window.parent.studyBackend) return window.parent.studyBackend;
  } catch { /* not our shell */ }
  const page = location.pathname.split("/").pop() || "today.html";
  location.replace(`./#${page}${location.search}${location.hash}`);
  return null;
}
const shell = BACKEND === "browser" ? findShell() : null;

function fail(status, text, fallback) {
  let detail = fallback || `Error ${status}`;
  try { detail = JSON.parse(text).detail ?? detail; } catch { /* not JSON */ }
  throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
}

async function request(path, options = {}) {
  if (BACKEND === "browser") {
    if (!shell) return new Promise(() => {});   // moving to the shell
    const { status, text } = await shell.call(options.method || "GET", path, options.body || "");
    if (status >= 400) fail(status, text);
    return status === 204 || !text ? null : JSON.parse(text);
  }
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) fail(res.status, await res.text(), res.statusText);
  if (res.status === 204) return null;
  return res.json();
}

export function fetchTree() {
  return request("/api/tree");
}

export function saveProgress(subjectId, { status, semester, grade }) {
  return request(`/api/progress/${encodeURIComponent(subjectId)}`, {
    method: "PUT",
    body: JSON.stringify({ status, semester, grade }),
  });
}

export function fetchDashboard(subjectId) {
  return request(`/api/subjects/${encodeURIComponent(subjectId)}/dashboard`);
}

export function updateTopic(topicId, changes) {
  return request(`/api/topics/${encodeURIComponent(topicId)}`, {
    method: "PUT",
    body: JSON.stringify(changes),
  });
}

export const fetchOverview = () => request("/api/overview");

const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body ?? {}) });
const del = (path) => request(path, { method: "DELETE" });
const enc = encodeURIComponent;

export const addExam = (subjectId, exam) => post(`/api/subjects/${enc(subjectId)}/exams`, exam);
export const deleteExam = (examId) => del(`/api/exams/${examId}`);
export const logSession = (topicId, minutes) => post(`/api/topics/${enc(topicId)}/sessions`, { minutes });
export const addCard = (topicId, card) => post(`/api/topics/${enc(topicId)}/cards`, card);
export const deleteCard = (cardId) => del(`/api/cards/${cardId}`);
export const reviewCard = (cardId, result) => post(`/api/cards/${cardId}/review`, { result });
export const addResource = (topicId, resource) => post(`/api/topics/${enc(topicId)}/resources`, resource);
export const deleteResource = (resourceId) => del(`/api/resources/${resourceId}`);
export const tickPracticeExam = (examId, done) =>
  request(`/api/practice-exams/${enc(examId)}`, { method: "PUT", body: JSON.stringify({ done }) });
export function fetchPractice(subjectId, topicId) {
  const q = topicId ? `?topic_id=${enc(topicId)}` : "";
  return request(`/api/subjects/${enc(subjectId)}/practice${q}`);
}

export const fetchToday = () => request("/api/today");
export const tickPlanItem = (key, done) =>
  request(`/api/today/ticks/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify({ done }) });
export const addToPlan = () => request("/api/today/more", { method: "POST", body: "{}" });
export const rebuildPlan = () => request("/api/today/rebuild", { method: "POST", body: "{}" });
export const fetchReview = (subjectId) => request(`/api/subjects/${encodeURIComponent(subjectId)}/review`);
export const downloadBackup = () => request("/api/backup");
export const restoreBackup = (backup) => request("/api/backup", { method: "POST", body: JSON.stringify(backup) });
export const savePracticeResult = (examId, result) =>
  request(`/api/practice-exams/${encodeURIComponent(examId)}/result`, { method: "PUT", body: JSON.stringify(result) });
export const saveSettings = (settings) => request("/api/settings", { method: "PUT", body: JSON.stringify(settings) });
