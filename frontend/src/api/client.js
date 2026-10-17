// Thin fetch wrapper. Every call is timed; server timings_ms are kept for the ?debug=1 panel.
const BASE = "/api/v1";
const log = [];
const subs = new Set();

export function onApiLog(fn) { subs.add(fn); return () => subs.delete(fn); }
export function apiLog() { return log; }

function record(entry) {
  log.unshift(entry);
  if (log.length > 40) log.pop();
  subs.forEach((f) => f(log));
}

export class ApiError extends Error {
  constructor(status, detail) { super(`${status}: ${detail}`); this.status = status; this.detail = detail; }
}

async function call(method, path, { json, form, signal } = {}) {
  const t0 = performance.now();
  const opts = { method, signal, headers: {} };
  if (json !== undefined) { opts.body = JSON.stringify(json); opts.headers["Content-Type"] = "application/json"; }
  if (form) opts.body = form;
  let res;
  try {
    res = await fetch(BASE + path, opts);
  } catch (e) {
    record({ method, path, ms: Math.round(performance.now() - t0), status: "network", at: Date.now() });
    throw new ApiError(0, e.message);
  }
  const ms = Math.round(performance.now() - t0);
  let body = null;
  try { body = await res.json(); } catch { /* empty body */ }
  record({ method, path: path.split("?")[0], ms, status: res.status, server: body?.timings_ms, at: Date.now() });
  if (!res.ok) throw new ApiError(res.status, body?.detail || res.statusText);
  return body;
}

const enc = encodeURIComponent;

export const api = {
  config: () => call("GET", "/config"),
  newSession: (lang) => call("POST", "/sessions", { json: { lang } }),
  session: (sid, lang) => call("GET", `/sessions/${sid}?lang=${lang}`),
  setLang: (sid, lang) => call("PATCH", `/sessions/${sid}`, { json: { lang } }),
  questions: (lang) => call("GET", `/questions?lang=${lang}`),
  question: (sid, field, lang) => call("GET", `/conversation/${sid}/question/${field}?lang=${lang}`),
  answer: (sid, body) => call("POST", `/conversation/${sid}/answer`, { json: body }),
  answerAudio: (sid, field, lang, blob) => {
    const f = new FormData();
    f.append("field", field); f.append("lang", lang); f.append("audio", blob, "answer.wav");
    return call("POST", `/conversation/${sid}/answer-audio`, { form: f });
  },
  back: (sid) => call("POST", `/conversation/${sid}/back`),
  uploadReport: (sid, file) => {
    const f = new FormData(); f.append("file", file, file.name);
    return call("POST", `/reports/${sid}`, { form: f });
  },
  patchReport: (sid, vals) => call("PATCH", `/profile/${sid}/report`, { json: vals }),
  profile: (sid, lang) => call("GET", `/profile/${sid}?lang=${lang}`),
  patchProfile: (sid, lang, body) => call("PATCH", `/profile/${sid}?lang=${lang}`, { json: body }),
  confirm: (sid) => call("POST", `/profile/${sid}/confirm`),
  context: (sid) => call("GET", `/context/${sid}`),
  recommend: (sid, lang) => call("POST", "/recommendations", { json: { session_id: sid, lang } }),
  recommendation: (rid, lang) => call("GET", `/recommendations/${rid}?lang=${lang}`),
  explain: (rid, lang) => call("POST", `/recommendations/${rid}/explain`, { json: { lang } }),
  plan: (rid, crop, lang) => call("POST", "/plans", { json: { recommendation_id: rid, crop_id: crop, lang } }),
  getPlan: (pid, lang) => call("GET", `/plans/${pid}?lang=${lang}`),
  ask: (pid, text, lang) => call("POST", "/assistant", { json: { plan_id: pid, text, lang } }),
  askAudio: (pid, lang, blob) => {
    const f = new FormData(); f.append("plan_id", pid); f.append("lang", lang); f.append("audio", blob, "q.wav");
    return call("POST", "/assistant/audio", { form: f });
  },
  tts: (text, lang) => call("POST", "/tts", { json: { text, lang } }),
  ttsPrefetch: (texts, lang) => call("POST", "/tts/prefetch", { json: { texts, lang } }),
};
export { enc };
