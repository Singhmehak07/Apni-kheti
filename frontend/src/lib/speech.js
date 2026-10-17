// One shared speech channel: server TTS (Sarvam, cached mp3) when available, else the browser voice.
import { api } from "../api/client.js";

const BCP = { pa: "pa-IN", hi: "hi-IN", en: "en-IN" };
const cache = new Map();          // lang|text -> {provider, urls, text}
const listeners = new Set();
let provider = "browser";
let current = null;               // token of the active utterance
let audio = null;
let watchdog = null;

// Eagerly cache browser voices on startup and on voice changes
let voicesCache = [];
function refreshVoices() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    const vs = window.speechSynthesis.getVoices();
    if (vs && vs.length) voicesCache = vs;
  }
}
if (typeof window !== "undefined" && "speechSynthesis" in window) {
  refreshVoices();
  window.speechSynthesis.onvoiceschanged = refreshVoices;
}

export function setTtsProvider(p) { provider = p || "browser"; }
export function onSpeaking(fn) { listeners.add(fn); return () => listeners.delete(fn); }
const emit = (id) => listeners.forEach((f) => f(id));

export function browserVoiceAvailable(lang) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return false;
  const vs = voicesCache.length ? voicesCache : window.speechSynthesis.getVoices();
  return vs.length === 0 || vs.some((v) => v.lang?.toLowerCase().startsWith(lang));
}

function pickVoice(lang) {
  const vs = (voicesCache.length ? voicesCache : window.speechSynthesis?.getVoices?.()) || [];
  if (!vs.length) return null;
  const want = BCP[lang]?.toLowerCase();
  // 1. Direct language code match (e.g. pa-IN)
  let v = vs.find((x) => x.lang?.toLowerCase() === want);
  if (v) return v;
  // 2. Starts with language code (e.g. pa)
  v = vs.find((x) => x.lang?.toLowerCase().startsWith(lang));
  if (v) return v;
  // 3. Indian subcontinent voice fallback for pa (Punjabi) -> hi-IN or en-IN
  if (lang === "pa") {
    v = vs.find((x) => x.lang?.toLowerCase() === "hi-in" || x.lang?.toLowerCase().startsWith("hi"));
    if (v) return v;
    v = vs.find((x) => x.lang?.toLowerCase() === "en-in");
    if (v) return v;
  }
  // 4. Default or first available voice
  return vs.find((x) => x.default) || vs[0] || null;
}

function cleanTextForSpeech(text) {
  if (!text) return "";
  return text
    .replace(/[()]/g, " ")
    .replace(/[•·/]/g, " ")
    .replace(/(\d)\s*[–-]\s*(\d)/g, "$1 to $2")
    .replace(/\s+/g, " ")
    .trim();
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
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return resolve(false);
    const synth = window.speechSynthesis;
    try {
      synth.cancel();
      if (synth.paused) synth.resume();
    } catch { /* ignore */ }

    const cleaned = cleanTextForSpeech(text);
    const chunks = splitSentences(cleaned || text);
    let i = 0;

    const stopWatchdog = () => {
      if (watchdog) {
        clearInterval(watchdog);
        watchdog = null;
      }
    };

    const next = () => {
      if (current !== token || i >= chunks.length) {
        stopWatchdog();
        return resolve(true);
      }
      const u = new SpeechSynthesisUtterance(chunks[i++]);
      u.lang = BCP[lang] || "pa-IN";
      u.rate = 1.0;
      const v = pickVoice(lang);
      if (v) u.voice = v;

      u.onend = next;
      u.onerror = (e) => {
        stopWatchdog();
        resolve(e?.error === "canceled");
      };

      stopWatchdog();
      watchdog = setInterval(() => {
        if (!synth.speaking) {
          stopWatchdog();
        } else if (synth.paused) {
          synth.resume();
        }
      }, 500);

      try {
        synth.speak(u);
        synth.resume();
      } catch {
        stopWatchdog();
        resolve(false);
      }
    };

    // 15ms yield unfreezes Chromium's cancel-speak deadlock
    setTimeout(() => {
      if (current !== token) {
        stopWatchdog();
        return resolve(false);
      }
      try {
        if (synth.paused) synth.resume();
      } catch { /* ignore */ }
      next();
    }, 15);
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
  if (watchdog) { clearInterval(watchdog); watchdog = null; }
  if (audio) { audio.pause(); audio = null; }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
      if (window.speechSynthesis.paused) window.speechSynthesis.resume();
    } catch { /* ignore */ }
  }
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
