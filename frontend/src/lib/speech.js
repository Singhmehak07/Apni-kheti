// One shared speech channel: server TTS (Sarvam, cached mp3) when available, else the browser voice.
import { api } from "../api/client.js";

const BCP = { pa: "pa-IN", hi: "hi-IN", en: "en-IN" };
const cache = new Map();          // lang|text -> {provider, urls, text}
const listeners = new Set();
let provider = "browser";
let current = null;               // token of the active utterance
let audio = null;

export function setTtsProvider(p) { provider = p || "browser"; }
export function onSpeaking(fn) { listeners.add(fn); return () => listeners.delete(fn); }
const emit = (id) => listeners.forEach((f) => f(id));

export function browserVoiceAvailable(lang) {
  if (!("speechSynthesis" in window)) return false;
  const vs = window.speechSynthesis.getVoices();
  return vs.length === 0 || vs.some((v) => v.lang?.toLowerCase().startsWith(lang));
}

function pickVoice(lang) {
  const vs = window.speechSynthesis?.getVoices?.() || [];
  const want = BCP[lang].toLowerCase();
  return vs.find((v) => v.lang?.toLowerCase() === want) || vs.find((v) => v.lang?.toLowerCase().startsWith(lang)) || null;
}

function splitSentences(text) {
  const parts = text.split(/(?<=[।.!?])\s+/).filter(Boolean);
  const out = [];
  for (const p of parts) {
    if (out.length && (out[out.length - 1] + " " + p).length < 180) out[out.length - 1] += " " + p;
    else out.push(p);
  }
  return out.length ? out : [text];
}

function speakBrowser(text, lang, token) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) return resolve(false);
    const synth = window.speechSynthesis;
    synth.cancel();
    const chunks = splitSentences(text);
    let i = 0;
    const next = () => {
      if (current !== token || i >= chunks.length) return resolve(true);
      const u = new SpeechSynthesisUtterance(chunks[i++]);
      u.lang = BCP[lang]; u.rate = 0.92;
      const v = pickVoice(lang); if (v) u.voice = v;
      u.onend = next; u.onerror = () => resolve(false);
      synth.speak(u);
    };
    next();
  });
}

function playUrl(url, token) {
  return new Promise((resolve, reject) => {
    if (current !== token) return resolve();
    audio = new Audio(url);
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error("audio failed"));
    audio.play().catch(reject);
  });
}

async function serverTts(text, lang) {
  const key = `${lang}|${text}`;
  if (!cache.has(key)) cache.set(key, api.tts(text, lang).catch((e) => { cache.delete(key); throw e; }));
  return cache.get(key);
}

/** Warm the cache (and the browser's HTTP cache) for texts that will likely be spoken next. */
export function warm(texts, lang) {
  if (provider === "browser") return;
  texts.filter(Boolean).slice(0, 12).forEach((t) =>
    serverTts(t, lang).then((r) => r.urls?.forEach((u) => { const a = new Audio(); a.preload = "auto"; a.src = u; })).catch(() => {}));
}

export function stop() {
  current = null;
  if (audio) { audio.pause(); audio = null; }
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  emit(null);
}

/** Speak text; resolves when finished or interrupted. id lets buttons show their own playing state. */
export async function speak(text, lang, id = text) {
  if (!text) return;
  stop();
  const token = { id };
  current = token;
  emit(id);
  try {
    if (provider !== "browser") {
      const r = await serverTts(text, lang);
      if (r.provider !== "browser" && r.urls?.length) {
        for (const u of r.urls) { if (current !== token) return; await playUrl(u, token); }
        return;
      }
    }
    await speakBrowser(text, lang, token);
  } catch {
    if (current === token) await speakBrowser(text, lang, token);
  } finally {
    if (current === token) { current = null; emit(null); }
  }
}

export function isSpeaking(id) { return current?.id === id; }
