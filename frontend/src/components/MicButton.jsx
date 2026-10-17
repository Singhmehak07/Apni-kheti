import { useEffect, useRef, useState } from "react";
import { Mic, Square, LoaderCircle } from "lucide-react";
import { useApp } from "../context.js";
import { browserRecognize, browserSttSupported, micSupported, startRecording } from "../lib/recorder.js";
import { stop as stopSpeech } from "../lib/speech.js";

/** Which voice path this device can use: server STT (WAV upload) or the browser recogniser. */
export function voiceMode(config) {
  if (!config) return null;
  if (config.stt_provider && config.stt_provider !== "browser" && micSupported()) return "server";
  if (browserSttSupported()) return "browser";
  return null;
}

/**
 * Big mic button. onResult receives {blob} (server mode) or {transcript} (browser mode).
 * The parent does the upload and calls back with the outcome; `busy` shows the processing state.
 */
export default function MicButton({ onResult, busy = false, size = "lg", hint = true, label, autoStart = 0 }) {
  const { t, config, lang, notify } = useApp();
  const mode = voiceMode(config);
  const [state, setState] = useState("idle"); // idle | listening
  const [level, setLevel] = useState(0);
  const ctl = useRef(null);
  const lastAutoStart = useRef(0);

  useEffect(() => () => ctl.current?.stop?.(), []);

  useEffect(() => {
    if (autoStart && autoStart !== lastAutoStart.current) {
      lastAutoStart.current = autoStart;
      if (mode && !busy && state === "idle") {
        begin();
      }
    }
  }, [autoStart, mode, busy, state]);

  if (!mode) return null;

  async function begin() {
    stopSpeech();
    setState("listening");
    try {
      if (mode === "server") {
        const r = startRecording({ maxMs: (config.max_audio_s || 25) * 1000, onLevel: setLevel });
        ctl.current = r;
        const out = await r.done;
        setState("idle"); setLevel(0);
        if (!out.speech && out.reason === "no_speech") { notify(t("noSpeech"), "warn"); return; }
        onResult({ blob: out.blob, ms: out.ms });
      } else {
        const r = browserRecognize(lang);
        ctl.current = r;
        const out = await r.done;
        setState("idle");
        if (!out.transcript) { notify(t("noSpeech"), "warn"); return; }
        onResult({ transcript: out.transcript });
      }
    } catch (e) {
      setState("idle"); setLevel(0);
      const denied = /denied|NotAllowed|not-allowed|Permission/i.test(String(e?.name || e?.message));
      notify(denied ? t("micDenied") : t("voiceFailed"), "warn");
    } finally { ctl.current = null; }
  }

  const listening = state === "listening";
  const big = size === "lg";
  const dim = big ? "h-[76px] w-[76px]" : "h-12 w-12";
  const caption = busy ? t("understanding") : listening ? t("listening") : t("tapToSpeak");
  return (
    <div className={`flex items-center ${big ? "flex-col gap-2" : "gap-2"}`}>
      <button
        type="button"
        data-testid="mic"
        onClick={() => (listening ? ctl.current?.stop() : begin())}
        disabled={busy}
        aria-label={listening ? t("tapToStop") : label || t("tapToSpeak")}
        className={`relative inline-flex items-center justify-center rounded-full ${dim} text-white shadow-sm transition-colors disabled:opacity-60 ${listening ? "bg-red" : "bg-ink hover:bg-black"}`}
      >
        {listening && <span className="mic-ring" style={{ transform: `scale(${1 + level * 0.5})` }} aria-hidden />}
        <span className="relative">
          {busy ? <LoaderCircle className="animate-spin" size={big ? 32 : 22} aria-hidden />
            : listening ? <Square size={big ? 26 : 18} fill="currentColor" aria-hidden />
            : <Mic size={big ? 34 : 22} strokeWidth={2} aria-hidden />}
        </span>
      </button>
      {hint && <span className={`text-[15px] font-semibold ${listening ? "text-red-ink" : "text-muted"}`} aria-live="polite">{caption}</span>}
    </div>
  );
}
