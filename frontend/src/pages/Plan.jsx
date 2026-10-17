import { useState } from "react";
import { ArrowLeft, RotateCcw, Send, Phone, Check, LoaderCircle } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import { speak } from "../lib/speech.js";
import Icon, { CROP_TONE } from "../components/Icon.jsx";
import SpeakButton from "../components/SpeakButton.jsx";
import MicButton from "../components/MicButton.jsx";
import Stepper from "../components/Stepper.jsx";
import { num, rs } from "../lib/format.js";

function AskBox({ plan }) {
  const { t, lang, autoRead, notify } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [qa, setQa] = useState([]);
  const push = (q, r) => {
    setQa((x) => [...x, { q, a: r.answer, id: Date.now() }]);
    if (autoRead) speak(r.answer, lang, `ans-${Date.now()}`);
  };
  const ask = async (q) => {
    setBusy(true);
    try { push(q, await api.ask(plan.id, q, lang)); setText(""); }
    catch { notify(t("error"), "warn"); } finally { setBusy(false); }
  };
  const voice = async ({ blob, transcript }) => {
    if (transcript) return ask(transcript);
    setBusy(true);
    try {
      const r = await api.askAudio(plan.id, lang, blob);
      if (!r.transcript) { notify(t("noSpeech"), "warn"); return; }
      push(r.transcript, r);
    } catch (e) { notify(e.status === 503 ? t("voiceFailed") : t("error"), "warn"); } finally { setBusy(false); }
  };
  return (
    <section className="card space-y-3 p-4" data-testid="ask">
      <h2 className="text-[19px] font-bold" data-read={t("askTitle")}>{t("askTitle")}</h2>
      {qa.map((x) => (
        <div key={x.id} className="space-y-2">
          <p className="ml-8 rounded-[8px] bg-sunken px-3 py-2 text-right font-semibold">{x.q}</p>
          <div className="mr-4 flex items-start gap-2 rounded-[8px] bg-blue-soft px-3 py-2">
            <p className="flex-1" data-testid="answer">{x.a}</p>
            <SpeakButton text={x.a} size="sm" tone="quiet" />
          </div>
        </div>
      ))}
      {busy && <p className="flex items-center gap-2 text-muted"><LoaderCircle className="animate-spin" size={18} aria-hidden />{t("thinking")}</p>}
      <div className="flex items-center gap-2">
        <MicButton onResult={voice} busy={busy} size="sm" hint={false} label={t("askTitle")} />
        <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) ask(text.trim()); }}>
          <input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("askPh")} data-testid="ask-input" />
          <button className="btn-primary min-h-12 shrink-0" disabled={busy || !text.trim()} data-testid="ask-send"><Send size={18} aria-hidden /><span className="max-sm:sr-only">{t("ask")}</span></button>
        </form>
      </div>
      <p className="flex items-center gap-2 text-[14px] text-muted"><Phone size={15} aria-hidden /><a href="tel:18001801551" className="underline">{t("helpline")}</a></p>
    </section>
  );
}

export default function Plan({ plan, onBack, onRestart }) {
  const { t } = useApp();
  const tone = CROP_TONE[plan.color] || CROP_TONE.green;
  const s = plan.summary || {};
  const whole = [t("planTitle", { crop: plan.name }), ...plan.steps.map((st) => `${st.when}: ${st.title}. ${st.text}`)].join("। ");
  return (
    <main className="pb-24">
      <Stepper index={4} />
      <div className="mx-auto max-w-3xl space-y-4 px-4 pt-5">
        <button type="button" className="btn-ghost -ml-2 px-2" onClick={onBack} data-testid="other-crops"><ArrowLeft size={20} aria-hidden />{t("otherCrops")}</button>
        <section className="card p-5">
          <div className="flex items-start gap-3">
            <span className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-[8px] ${tone.bg} ${tone.text}`}><Icon name={plan.crop_id} size={26} /></span>
            <div className="min-w-0 flex-1">
              <h1 className="text-[24px] font-bold leading-tight" data-read={t("planTitle", { crop: plan.name })}>{t("planTitle", { crop: plan.name })}</h1>
              <p className="text-muted">{plan.variety} · {num(plan.acres)} {t("perAcreShort").replace("/", "")} · {t("sowOn")} {plan.sow_date_label} · {t("harvest")} {plan.harvest_label}</p>
            </div>
          </div>
          {s.net_total && (
            <div className="mt-4 rounded-[8px] bg-canvas p-3.5">
              <p className="text-[14px] text-muted">{t("expected")}</p>
              <p className="text-[28px] font-bold tabular-nums">{rs(s.net_total.base)}</p>
              <p className="text-[14px] text-muted">{t("badYear")} {rs(s.net_total.low)} · {t("goodYear")} {rs(s.net_total.high)}</p>
            </div>
          )}
          <div className="mt-4"><SpeakButton text={whole} id="plan-all" showText size="lg" caption={t("readPlan")} label={t("readPlan")} className="w-full sm:w-auto" /></div>
        </section>

        <ol className="relative space-y-3" data-testid="timeline">
          {plan.steps.map((st) => {
            const now = st.state === "now", done = st.state === "done";
            return (
              <li key={st.id} className={`card flex gap-3 p-4 ${now ? "border-blue ring-1 ring-blue" : ""} ${done ? "opacity-70" : ""}`} data-testid={`step-${st.id}`}>
                <span className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${done ? "bg-green-soft text-green-ink" : now ? "bg-blue-ink text-white" : "bg-sunken text-ink"}`}>
                  {done ? <Check size={20} aria-hidden /> : <Icon name={st.icon} size={21} />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-[14px] font-semibold text-muted">
                    <span>{st.when}</span>
                    {now && <span className="chip bg-blue-ink text-white">{t("now")}</span>}
                    {done && <span className="chip bg-green-soft text-green-ink">{t("done")}</span>}
                  </p>
                  <h3 className="text-[18px] font-bold" data-read={`${st.when}. ${st.title}`}>{st.title}</h3>
                  <p className="mt-0.5" data-read={st.text}>{st.text}</p>
                </div>
                <SpeakButton text={`${st.title}. ${st.when}. ${st.text}`} id={`step-${st.id}`} size="sm" tone="quiet" label={st.title} />
              </li>
            );
          })}
        </ol>

        <AskBox plan={plan} />
        <p className="rounded-[8px] bg-sunken px-4 py-3 text-[15px] text-muted">{t("estimateNote")}</p>
        <button type="button" className="btn-secondary" onClick={onRestart} data-testid="restart"><RotateCcw size={18} aria-hidden />{t("startOver")}</button>
      </div>
    </main>
  );
}
