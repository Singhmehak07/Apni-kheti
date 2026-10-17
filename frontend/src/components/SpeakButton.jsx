import { useEffect, useState } from "react";
import { Volume2 } from "lucide-react";
import { useApp } from "../context.js";
import { onSpeaking, speak, stop } from "../lib/speech.js";

export function useSpeakingId() {
  const [id, setId] = useState(null);
  useEffect(() => onSpeaking(setId), []);
  return id;
}

function Bars() {
  return <span className="speaking-bars inline-flex items-center h-5" aria-hidden><span /><span /><span /></span>;
}

/** Speaker button. `text` is what is read; `label` names the thing for screen readers. */
export default function SpeakButton({ text, id, label, speakLang, caption, size = "md", className = "", tone = "default", showText = false }) {
  const { lang, t } = useApp();
  const key = id || text;
  const active = useSpeakingId() === key;
  const dims = size === "sm" ? "h-11 w-11" : size === "lg" ? "h-12 min-w-12" : "h-11 min-w-11";
  const tones = {
    default: active ? "bg-blue-ink text-white" : "bg-blue-soft text-blue-ink hover:bg-[#d3e8fa]",
    quiet: active ? "bg-blue-ink text-white" : "text-blue-ink hover:bg-blue-soft",
  };
  return (
    <button
      type="button"
      onPointerDown={() => {
        if (typeof window !== "undefined" && "speechSynthesis" in window) {
          try { window.speechSynthesis.resume(); } catch { /* ignore */ }
        }
      }}
      onClick={(e) => {
        e.stopPropagation();
        if (typeof window !== "undefined" && "speechSynthesis" in window) {
          try { window.speechSynthesis.resume(); } catch { /* ignore */ }
        }
        active ? stop() : speak(text, speakLang || lang, key);
      }}
      aria-label={`${active ? t("stop") : t("listen")}${label ? ": " + label : ""}`}
      aria-pressed={active}
      data-testid="speak"
      className={`inline-flex shrink-0 items-center justify-center gap-2 rounded-full ${dims} ${showText ? "px-4" : ""} transition-colors ${tones[tone]} ${className}`}
    >
      {active ? <Bars /> : <Volume2 size={size === "sm" ? 20 : 22} strokeWidth={2} aria-hidden />}
      {showText && <span className="font-semibold text-[15px]">{active ? t("stop") : caption || t("listen")}</span>}
    </button>
  );
}
