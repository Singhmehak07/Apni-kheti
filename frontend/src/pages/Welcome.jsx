import { ArrowRight, Mic, Scale, CalendarDays, FileText } from "lucide-react";
import { useApp } from "../context.js";
import S, { LANGS } from "../i18n/strings.js";
import SpeakButton from "../components/SpeakButton.jsx";
import Icon, { CROP_TONE } from "../components/Icon.jsx";

const CROPS = [["wheat", "orange"], ["raya", "yellow"], ["gram", "green"], ["barley", "blue"]];

export default function Welcome({ onStart, busy, canResume, onResume }) {
  const { t, lang } = useApp();
  const how = [[Mic, t("how1")], [Scale, t("how2")], [CalendarDays, t("how3")]];
  return (
    <main className="mx-auto max-w-3xl px-4 pb-16 pt-8">
      <section className="anim-in space-y-3">
        <h1 className="text-[32px] font-bold leading-tight sm:text-[38px]" data-read={t("appName")}>{t("appName")}</h1>
        <div className="flex items-start gap-3">
          <p className="max-w-xl text-[19px] text-muted" data-read={t("tagline")}>{t("tagline")}</p>
          <SpeakButton text={[t("tagline"), t("how1"), t("how2"), t("how3")].join("। ")} label={t("tagline")} />
        </div>
      </section>

      <section className="mt-7 space-y-3" aria-labelledby="lang-h">
        <h2 id="lang-h" className="text-[21px] font-bold" data-read={t("chooseLang")}>{t("chooseLang")}</h2>
        <ul className="grid gap-2.5 sm:grid-cols-3" role="list">
          {LANGS.map((l) => (
            <li key={l.id} lang={l.id} className={`card flex items-center gap-1 pr-2 ${lang === l.id ? "border-ink ring-2 ring-ink" : ""}`}>
              <button type="button" disabled={busy} onClick={() => onStart(l.id)} data-testid={`start-${l.id}`}
                className="flex min-h-20 flex-1 flex-col items-start justify-center px-4 py-3 text-left">
                <span className="text-[22px] font-bold leading-tight">{l.native}</span>
                <span className="text-[15px] leading-snug text-muted">{S.langContinue[l.id]}</span>
              </button>
              <SpeakButton text={S.langContinue[l.id]} speakLang={l.id} id={`lang-${l.id}`} label={l.native} />
            </li>
          ))}
        </ul>
        {canResume && (
          <button type="button" className="btn-secondary min-h-12" onClick={onResume} data-testid="resume">{t("resume")} <ArrowRight size={18} aria-hidden /></button>
        )}
        <p className="flex items-center gap-2 pt-2 text-[15px] text-muted" data-read={t("haveReport")}>
          <FileText size={18} aria-hidden /> {t("haveReport")}
        </p>
      </section>

      <div className="mt-9" aria-label={t("cropsCompared")}>
        <ul className="grid grid-cols-4 gap-2" role="list">
          {CROPS.map(([id, c]) => (
            <li key={id} className={`flex flex-col items-center gap-1.5 rounded-[8px] px-1 py-3 ${CROP_TONE[c].bg}`} data-read={t("crops")[id]}>
              <Icon name={id} size={30} className={CROP_TONE[c].text} />
              <span className={`text-center text-[14px] font-semibold leading-tight ${CROP_TONE[c].text}`}>{t("crops")[id]}</span>
            </li>
          ))}
        </ul>
      </div>

      <ol className="mt-3 grid gap-2.5 sm:grid-cols-3">
        {how.map(([I, txt], i) => (
          <li key={i} className="card flex items-start gap-3 p-4" data-read={txt}>
            <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-green-soft text-green-ink"><I size={21} aria-hidden /></span>
            <span className="font-semibold leading-snug">{txt}</span>
          </li>
        ))}
      </ol>

    </main>
  );
}
