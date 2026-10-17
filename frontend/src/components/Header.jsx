import { BookOpen, Sprout } from "lucide-react";
import { useApp } from "../context.js";
import { LANGS } from "../i18n/strings.js";
import { speak, stop } from "../lib/speech.js";
import { useSpeakingId } from "./SpeakButton.jsx";

/** Collect visible [data-read] texts in DOM order — powers "Read this screen". */
export function screenText() {
  const nodes = document.querySelectorAll("main [data-read]");
  return Array.from(nodes)
    .filter((n) => n.offsetParent !== null)
    .map((n) => (n.getAttribute("data-read") || n.textContent || "").trim())
    .filter(Boolean)
    .join("। ")
    .replace(/।\s*।/g, "।");
}

export default function Header({ onHome }) {
  const { lang, setLang, t } = useApp();
  const reading = useSpeakingId() === "__screen__";
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-2">
        <button type="button" onClick={onHome} className="flex min-h-11 items-center gap-2 rounded-[8px] pr-2 font-bold text-[17px]" aria-label={t("appName")}>
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-[8px] bg-green text-white"><Sprout size={19} aria-hidden /></span>
          <span className="hidden sm:inline">{t("appName")}</span>
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          <div role="group" aria-label={t("language")} className="flex rounded-[8px] border border-line bg-white p-0.5">
            {LANGS.map((l) => (
              <button key={l.id} type="button" lang={l.id} onClick={() => setLang(l.id)} aria-pressed={lang === l.id}
                data-testid={`lang-${l.id}`}
                className={`min-h-10 rounded-[6px] px-2.5 text-[15px] font-semibold transition-colors ${lang === l.id ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
                {l.native}
              </button>
            ))}
          </div>
          <button type="button" data-testid="read-screen"
            onClick={() => (reading ? stop() : speak(screenText(), lang, "__screen__"))}
            aria-pressed={reading}
            className={`inline-flex min-h-11 items-center gap-1.5 rounded-[8px] px-3 text-[15px] font-semibold transition-colors ${reading ? "bg-blue-ink text-white" : "bg-blue-soft text-blue-ink hover:bg-[#d3e8fa]"}`}>
            <BookOpen size={19} aria-hidden />
            <span className="hidden sm:inline">{reading ? t("stop") : t("readScreen")}</span>
            <span className="sr-only sm:hidden">{reading ? t("stop") : t("readScreen")}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
