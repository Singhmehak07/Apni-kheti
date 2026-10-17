import { useEffect, useRef, useState } from "react";
import { ArrowLeft, CircleHelp, CircleCheck, Pencil, Send, FileUp, MinusCircle } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import { speak, warm } from "../lib/speech.js";
import Icon from "../components/Icon.jsx";
import SpeakButton from "../components/SpeakButton.jsx";
import MicButton, { voiceMode } from "../components/MicButton.jsx";
import OptionGrid from "../components/OptionGrid.jsx";
import DistrictPicker from "../components/DistrictPicker.jsx";
import LandInput from "../components/LandInput.jsx";
import ReportUpload from "../components/ReportUpload.jsx";
import Stepper from "../components/Stepper.jsx";

export function AnswerWidget({ q, onOption, onValue, busy, selected }) {
  if (q.kind === "district") return <DistrictPicker options={q.options} onPick={onOption} disabled={busy} />;
  if (q.kind === "number") return <LandInput key={q.field} units={q.units || []} onSubmit={onValue} disabled={busy} />;
  return <OptionGrid options={q.options} onPick={onOption} disabled={busy} selected={selected} field={q.field} cols={q.options.length > 4 ? 3 : 2} />;
}

function TypeBox({ onSend, busy, initial = "", autoFocus = false, testid = "type-answer" }) {
  const { t } = useApp();
  const [v, setV] = useState(initial);
  useEffect(() => setV(initial), [initial]);
  return (
    <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); if (v.trim()) { onSend(v.trim()); setV(""); } }}>
      <label className="flex-1"><span className="sr-only">{t("orType")}</span>
        <input className="field" value={v} onChange={(e) => setV(e.target.value)} placeholder={t("orType")} data-testid={testid} autoFocus={autoFocus} enterKeyHint="send" />
      </label>
      <button className="btn-secondary min-h-12 w-12 shrink-0 p-0" disabled={busy || !v.trim()} aria-label={t("send")} data-testid={`${testid}-send`}><Send size={20} aria-hidden /></button>
    </form>
  );
}

export default function Interview({ sid, question, setQuestion, onDone, onExit, report, setReport }) {
  const { t, lang, config, autoRead, interacted, notify } = useApp();
  const [busy, setBusy] = useState(false);
  const [heard, setHeard] = useState(null);      // {text, field}
  const [fixing, setFixing] = useState(false);
  const [ack, setAck] = useState(null);          // {kind: ok|empty, items}
  const [pendingNext, setPendingNext] = useState(null); // shown after the upload card
  const qRef = useRef(null);
  const q = question;
  const uploading = pendingNext !== null;

  useEffect(() => {
    if (!q || uploading) return;
    warm([q.text, ...(q.options || []).slice(0, 8).map((o) => o.label)], lang);
    if (autoRead && interacted.current) speak(q.text, lang, `q-${q.field}`);
    qRef.current?.focus({ preventScroll: true });
  }, [q?.field, q?.attempt, q?.text, uploading]); // eslint-disable-line react-hooks/exhaustive-deps

  function handle(res) {
    if (res.result === "no_speech") { notify(t("noSpeech"), "warn"); if (res.next) setQuestion(res.next); return; }
    if (res.understood?.length) setAck({ kind: "ok", items: res.understood });
    else if (res.result === "not_available" || res.result === "not_provided") setAck({ kind: "empty", items: [{ label: q.label }] });
    else setAck(null);
    if (res.action === "upload_report") { setPendingNext(res.done ? "done" : res.next); return; }
    if (res.done) { onDone(); return; }
    if (res.next) setQuestion(res.next);
  }

  async function run(fn) {
    setBusy(true);
    try { handle(await fn()); }
    catch (e) { notify(e.status === 503 ? t("voiceFailed") : e.status === 0 ? t("offline") : t("error"), "warn"); }
    finally { setBusy(false); }
  }

  const answer = (body) => run(() => api.answer(sid, { field: q.field, ...body }));
  const onOption = (o) => { setHeard(null); answer({ option_id: o.id, via: "chip" }); };
  const onValue = (value) => { setHeard(null); answer({ value, via: "stepper" }); };
  const onText = (text) => { setHeard(null); answer({ text, via: "typed" }); };
  const onSkip = () => { setHeard(null); answer({ skip: true, via: "chip" }); };
  const onVoice = ({ blob, transcript }) => {
    const field = q.field;
    if (transcript) { setHeard({ text: transcript, field }); return answer({ text: transcript, via: "voice_browser" }); }
    run(async () => {
      const r = await api.answerAudio(sid, field, lang, blob);
      setHeard(r.transcript ? { text: r.transcript, field } : null);
      return r;
    });
  };
  const onFix = async (text) => {
    setFixing(false);
    if (heard.field === q.field) { setHeard({ ...heard, text }); return answer({ text, via: "typed" }); }
    setBusy(true);
    try {
      const r = await api.patchProfile(sid, lang, { field: heard.field, text });
      setHeard({ ...heard, text });
      if (r.result === "unclear") { notify(r.next?.text || t("error"), "warn"); return; }
      const item = r.profile.items.find((i) => i.field === heard.field);
      setAck(item ? { kind: item.display ? "ok" : "empty", items: [{ label: item.label, display: item.display }] } : null);
      const s = await api.session(sid, lang);
      if (s.done) onDone(); else setQuestion(s.question);
    } catch { notify(t("error"), "warn"); } finally { setBusy(false); }
  };
  const onBack = async () => {
    setHeard(null); setAck(null); setPendingNext(null);
    setBusy(true);
    try {
      const r = await api.back(sid);
      if (r.question) setQuestion(r.question); else onExit();
    } catch { notify(t("error"), "warn"); } finally { setBusy(false); }
  };
  const afterUpload = async () => {
    const n = pendingNext; setPendingNext(null);
    if (n === "done") onDone(); else if (n) setQuestion(n);
  };
  const uploadNow = async (r) => {   // uploaded straight from the first question
    setReport(r);
    const s = await api.session(sid, lang);
    setAck({ kind: "ok", items: [{ label: t("prov_report"), display: t("readOk", { n: r.count }) }] });
    if (s.done) onDone(); else setQuestion(s.question);
  };

  if (!q) return null;
  const retry = q.attempt > 0;
  const progress = Math.round((q.progress.done / Math.max(1, q.progress.total)) * 100);
  const hasVoice = !!voiceMode(config);

  return (
    <main className="pb-24">
      <Stepper index={0} />
      <div className="mx-auto max-w-3xl space-y-4 px-4 pt-5">
        <div className="flex items-center gap-3">
          <button type="button" className="btn-ghost -ml-2 px-2" onClick={onBack} disabled={busy} data-testid="back">
            <ArrowLeft size={20} aria-hidden /> {t("back")}
          </button>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-[14px] font-semibold text-muted" data-testid="progress">{t("questionOf", { n: Math.min(q.progress.done + 1, q.progress.total), t: q.progress.total })}</span>
            <span className="h-1.5 w-24 overflow-hidden rounded-full bg-line" aria-hidden><span className="block h-full bg-green transition-all" style={{ width: `${progress}%` }} /></span>
          </div>
        </div>

        {ack && (
          <div className={`anim-in flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[8px] px-4 py-2.5 text-[15px] ${ack.kind === "ok" ? "bg-green-soft text-green-ink" : "bg-sunken text-muted"}`} data-testid="ack" role="status">
            {ack.kind === "ok" ? <CircleCheck size={18} aria-hidden /> : <MinusCircle size={18} aria-hidden />}
            <span className="font-semibold">{ack.kind === "ok" ? t("gotIt") : t("leftEmpty")}</span>
            {ack.items.map((u, i) => (
              <span key={i}>{u.label}{u.display ? <>: <b>{u.display}</b></> : null}</span>
            ))}
          </div>
        )}

        {heard && (
          <div className="card flex flex-wrap items-center gap-2 px-4 py-2.5" data-testid="heard">
            <span className="text-[14px] font-semibold text-muted">{t("weHeard")}:</span>
            {fixing ? <TypeBox initial={heard.text} onSend={onFix} busy={busy} autoFocus testid="fix-input" />
              : <>
                <span className="flex-1 font-semibold">“{heard.text}”</span>
                <button type="button" className="btn-ghost min-h-10 px-2.5 text-[15px]" onClick={() => setFixing(true)} data-testid="fix"><Pencil size={16} aria-hidden />{t("fix")}</button>
              </>}
          </div>
        )}

        {uploading ? (
          <ReportUpload sid={sid} report={report} onReport={setReport} onContinue={afterUpload} onSkip={afterUpload} />
        ) : (
          <>
            <section key={`${q.field}-${q.attempt}`} className={`card anim-in p-5 ${retry ? "border-[#f2d6bf] bg-[#FFFBF7]" : ""}`} aria-live="polite">
              <div className="flex items-center gap-2 text-muted">
                <Icon name={q.icon} size={18} />
                <span className="label-sm">{q.label}</span>
              </div>
              <div className="mt-2 flex items-start gap-3">
                <h1 ref={qRef} tabIndex={-1} className="flex-1 text-[23px] font-bold leading-snug outline-none sm:text-[26px]" data-read={q.text} data-testid="question">{q.text}</h1>
                <SpeakButton text={q.text} id={`q-${q.field}`} size="lg" label={q.label} />
              </div>
              <div className={`mt-5 flex gap-4 ${hasVoice ? "flex-col items-center sm:flex-row sm:items-center" : ""}`}>
                {hasVoice && <MicButton onResult={onVoice} busy={busy} />}
                <TypeBox onSend={onText} busy={busy} />
              </div>
            </section>

            <AnswerWidget q={q} onOption={onOption} onValue={onValue} busy={busy} />

            {q.field === "soil_report" && (
              <ReportUpload sid={sid} report={report} onReport={uploadNow} compact />
            )}

            <div className="flex items-center gap-2">
              <button type="button" className="btn-secondary min-h-12 flex-1" onClick={onSkip} disabled={busy} data-testid="skip" data-read={q.dont_know_label}>
                <CircleHelp size={20} aria-hidden /> {q.dont_know_label}
              </button>
              <SpeakButton text={q.dont_know_label} label={q.dont_know_label} />
            </div>
          </>
        )}
      </div>
    </main>
  );
}
