// Small wrapper around the backend's JSON API.

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
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
