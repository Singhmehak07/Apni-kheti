import { useState, useMemo } from "react";
import { ArrowLeft, RotateCcw, Send, Phone, Check, LoaderCircle, Bell, Calendar, Download, ShieldAlert, FlaskConical } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import { speak } from "../lib/speech.js";
import Icon, { CROP_TONE } from "../components/Icon.jsx";
import SpeakButton from "../components/SpeakButton.jsx";
import MicButton from "../components/MicButton.jsx";
import Stepper from "../components/Stepper.jsx";
import { num, rs } from "../lib/format.js";

function downloadCalendar(plan) {
  const items = plan.reminders || [];
  if (!items.length) return;
  const events = items.map((r, idx) => {
    const dt = (r.start || "").replace(/-/g, "");
    const title = `${r.category === "fertilizer" ? "🧪 Fertiliser" : "🛡️ Pesticide"}: ${r.title} (${plan.name})`;
    const desc = `${r.text}\\n${r.dosage ? "Dose: " + r.dosage : ""}`;
    return [
      "BEGIN:VEVENT",
      `UID:apni-kheti-${plan.id}-${r.id}-${idx}@apnikheti.in`,
      `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").split(".")[0]}Z`,
      `DTSTART;VALUE=DATE:${dt}`,
      `DTEND;VALUE=DATE:${dt}`,
      `SUMMARY:${title}`,
      `DESCRIPTION:${desc}`,
      "BEGIN:VALARM",
      "ACTION:DISPLAY",
      "DESCRIPTION:Agricultural reminder: Application scheduled for today",
      "TRIGGER:-PT1H",
      "END:VALARM",
      "END:VEVENT"
    ].join("\r\n");
  }).join("\r\n");

  const ics = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Apni Kheti//Crop Schedule Reminders//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    events,
    "END:VCALENDAR"
  ].join("\r\n");

  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${plan.crop_id}_schedule_reminders.ics`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ReminderSchedule({ plan }) {
  const { t } = useApp();
  const [filter, setFilter] = useState("all"); // all | fertilizer | pesticide
  const items = plan.reminders || [];
  const filtered = useMemo(() => {
    if (filter === "fertilizer") return items.filter((x) => x.category === "fertilizer");
    if (filter === "pesticide") return items.filter((x) => x.category === "pesticide");
    return items;
  }, [items, filter]);

  if (!items.length) return null;

  const audioText = items.map((r) => `${r.when}: ${r.title}. ${r.dosage ? r.dosage + ". " : ""}${r.text}`).join("। ");

  return (
    <section className="card p-5 border-2 border-emerald-600/30 bg-[#FBFDFB] space-y-4 shadow-sm" data-testid="reminder-schedule">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-800">
            <Bell size={22} className="animate-pulse" aria-hidden />
          </span>
          <div>
            <h2 className="text-[20px] font-bold text-ink flex items-center gap-2">
              {t("reminderSectionTitle")}
              <span className="rounded-full bg-emerald-600 text-white text-[12px] px-2 py-0.5 font-semibold">
                {items.length} {t("allReminders")}
              </span>
            </h2>
            <p className="text-[14px] text-muted">{t("reminderSubtitle")}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => downloadCalendar(plan)}
            className="btn-secondary text-[14px] min-h-10 py-1.5 px-3 flex items-center gap-2 border-emerald-600/40 text-emerald-900 hover:bg-emerald-50"
            title={t("addCalendar")}
          >
            <Calendar size={16} aria-hidden />
            <span>{t("addCalendar")}</span>
          </button>
          <SpeakButton text={audioText} id="reminders-audio" size="sm" showText caption={t("readReminders")} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-line">
        <button
          type="button"
          onClick={() => setFilter("all")}
          className={`chip text-[14px] font-semibold py-1 px-3 ${filter === "all" ? "bg-ink text-white" : "bg-sunken text-ink hover:bg-line"}`}
        >
          {t("allReminders")} ({items.length})
        </button>
        <button
          type="button"
          onClick={() => setFilter("fertilizer")}
          className={`chip text-[14px] font-semibold py-1 px-3 flex items-center gap-1.5 ${filter === "fertilizer" ? "bg-emerald-700 text-white" : "bg-emerald-50 text-emerald-900 hover:bg-emerald-100"}`}
        >
          <FlaskConical size={15} aria-hidden />
          <span>{t("fertOnly")} ({items.filter((x) => x.category === "fertilizer").length})</span>
        </button>
        <button
          type="button"
          onClick={() => setFilter("pesticide")}
          className={`chip text-[14px] font-semibold py-1 px-3 flex items-center gap-1.5 ${filter === "pesticide" ? "bg-amber-700 text-white" : "bg-amber-50 text-amber-900 hover:bg-amber-100"}`}
        >
          <ShieldAlert size={15} aria-hidden />
          <span>{t("pestOnly")} ({items.filter((x) => x.category === "pesticide").length})</span>
        </button>
      </div>

      <div className="space-y-2.5">
        {filtered.map((r) => {
          const isFert = r.category === "fertilizer";
          return (
            <div
              key={r.id}
              className={`rounded-lg p-3.5 border transition-all ${isFert ? "bg-white border-emerald-200" : "bg-[#FFFDF7] border-amber-200"}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="space-y-1 min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-[14px] text-muted">{r.when}</span>
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[12px] font-bold ${isFert ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>
                      {isFert ? <FlaskConical size={13} aria-hidden /> : <ShieldAlert size={13} aria-hidden />}
                      {isFert ? t("catFert") : t("catPest")}
                    </span>
                  </div>
                  <h3 className="font-bold text-[16px] text-ink">{r.title}</h3>
                  {r.dosage && (
                    <div className="rounded bg-canvas px-2.5 py-1 text-[13px] font-semibold text-ink inline-block">
                      <span className="text-muted mr-1.5">{t("dosageLabel")}</span>
                      <span className="text-emerald-900 font-bold">{r.dosage}</span>
                    </div>
                  )}
                  <p className="text-[14px] text-muted pt-0.5 leading-relaxed">{r.text}</p>
                </div>
                <SpeakButton text={`${r.when}. ${r.title}. ${r.dosage ? r.dosage + ". " : ""}${r.text}`} id={`rem-${r.id}`} size="sm" tone="quiet" />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

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

        {/* Dedicated Fertilizer & Pesticide Reminder Schedule */}
        <ReminderSchedule plan={plan} />

        <ol className="relative space-y-3" data-testid="timeline">
          {plan.steps.map((st) => {
            const now = st.state === "now", done = st.state === "done";
            const isFert = st.category === "fertilizer";
            const isPest = st.category === "pesticide";
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
                    {isFert && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-800">
                        <FlaskConical size={12} aria-hidden /> {t("catFert")}
                      </span>
                    )}
                    {isPest && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-900">
                        <ShieldAlert size={12} aria-hidden /> {t("catPest")}
                      </span>
                    )}
                  </p>
                  <h3 className="text-[18px] font-bold" data-read={`${st.when}. ${st.title}`}>{st.title}</h3>
                  {st.dosage && (
                    <p className="text-[13px] font-semibold text-emerald-800 bg-emerald-50 rounded px-2 py-0.5 my-1 inline-block">
                      {t("dosageLabel")} {st.dosage}
                    </p>
                  )}
                  <p className="mt-0.5" data-read={st.text}>{st.text}</p>
                </div>
                <SpeakButton text={`${st.title}. ${st.when}. ${st.dosage ? st.dosage + ". " : ""}${st.text}`} id={`step-${st.id}`} size="sm" tone="quiet" label={st.title} />
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
