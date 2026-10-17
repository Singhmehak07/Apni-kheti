import { useEffect, useState } from "react";
import { ArrowRight, Pencil, X, LoaderCircle } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import Icon from "../components/Icon.jsx";
import Provenance from "../components/Provenance.jsx";
import SpeakButton from "../components/SpeakButton.jsx";
import Stepper from "../components/Stepper.jsx";
import ReportUpload, { ReportSummary } from "../components/ReportUpload.jsx";
import { AnswerWidget } from "./Interview.jsx";

function Editor({ sid, field, onSaved, onCancel }) {
  const { t, lang, notify } = useApp();
  const [q, setQ] = useState(null);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  useEffect(() => { api.question(sid, field, lang).then(setQ).catch(() => notify(t("error"), "warn")); }, [field, lang]); // eslint-disable-line
  const save = async (body) => {
    setBusy(true);
    try {
      const r = await api.patchProfile(sid, lang, { field, ...body });
      if (r.result === "unclear") { notify(r.next?.text || t("error"), "warn"); return; }
      onSaved(r.profile);
    } catch { notify(t("error"), "warn"); } finally { setBusy(false); }
  };
  if (!q) return <div className="flex justify-center p-6"><LoaderCircle className="animate-spin text-muted" aria-hidden /></div>;
  return (
    <div className="space-y-3 border-t border-line bg-canvas p-4" data-testid={`editor-${field}`}>
      <div className="flex items-start gap-2">
        <p className="flex-1 text-[18px] font-semibold">{q.text}</p>
        <SpeakButton text={q.text} size="sm" label={q.label} />
      </div>
      <AnswerWidget q={q} busy={busy} onOption={(o) => save({ option_id: o.id })} onValue={(value) => save({ value })} />
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) save({ text: text.trim() }); }}>
        <input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("orType")} />
        <button className="btn-secondary min-h-12" disabled={busy || !text.trim()}>{t("save")}</button>
      </form>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-ghost" onClick={() => save({ clear: true })} disabled={busy}>{t("clearIt")}</button>
        <button type="button" className="btn-ghost ml-auto" onClick={onCancel}><X size={18} aria-hidden />{t("cancel")}</button>
      </div>
    </div>
  );
}

export default function Confirm({ sid, report, setReport, onConfirmed }) {
  const { t, lang, notify } = useApp();
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.profile(sid, lang).then((p) => { setProfile(p); if (p.report) setReport(p.report); }).catch(() => notify(t("error"), "warn")); }, [sid, lang]); // eslint-disable-line
  if (!profile) return <main className="flex justify-center p-16"><LoaderCircle className="animate-spin text-muted" aria-hidden /></main>;
  const items = profile.items.filter((i) => i.field !== "soil_report");
  const rep = report || profile.report;
  const hasRep = rep?.params && Object.keys(rep.params).length > 0;
  const summary = items.map((i) => `${i.label}: ${i.display || t("notGiven")}`).join("। ");
  const go = async () => {
    setBusy(true);
    try { await api.confirm(sid); onConfirmed(); } catch { notify(t("error"), "warn"); setBusy(false); }
  };
  return (
    <main className="pb-24">
      <Stepper index={1} />
      <div className="mx-auto max-w-3xl space-y-4 px-4 pt-5">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <h1 className="text-[26px] font-bold" data-read={t("confirmTitle")}>{t("confirmTitle")}</h1>
            <p className="text-muted" data-read={t("confirmSub")}>{t("confirmSub")}</p>
          </div>
          <SpeakButton text={`${t("confirmTitle")} ${summary}`} label={t("confirmTitle")} size="lg" />
        </div>

        <ul className="card divide-y divide-line overflow-hidden" role="list" data-testid="profile">
          {items.map((i) => (
            <li key={i.field} data-testid={`row-${i.field}`}>
              <div className="flex items-center gap-3 px-4 py-2.5">
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-sunken"><Icon name={i.icon} size={20} /></span>
                <div className="min-w-0 flex-1" data-read={`${i.label}: ${i.display || t("notGiven")}`}>
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[14px] text-muted">{i.label} <Provenance kind={i.provenance} /></p>
                  <p className={`text-[17px] font-semibold ${i.display ? "" : "text-muted"}`}>{i.display || t("notGiven")}</p>
                </div>
                <SpeakButton text={`${i.label}: ${i.display || t("notGiven")}`} size="sm" tone="quiet" label={i.label} />
                <button type="button" className="btn-secondary min-h-11 px-3 text-[15px]" onClick={() => setEditing(editing === i.field ? null : i.field)} data-testid={`change-${i.field}`}>
                  <Pencil size={16} aria-hidden /><span className="max-[380px]:sr-only">{t("change")}</span>
                </button>
              </div>
              {editing === i.field && (
                <Editor sid={sid} field={i.field} onCancel={() => setEditing(null)} onSaved={(p) => { setProfile(p); setEditing(null); }} />
              )}
            </li>
          ))}
        </ul>

        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-[19px] font-bold" data-read={t("soilValues")}>{t("soilValues")}</h2>
            {hasRep && <Provenance kind={rep.method === "manual" ? "manual" : "report"} />}
          </div>
          {hasRep ? <div className="card p-4"><ReportSummary report={rep} /></div>
            : <ReportUpload sid={sid} report={rep} onReport={(r) => { setReport(r); api.profile(sid, lang).then(setProfile); }} compact showManual />}
        </section>

        <p className="text-[15px] text-muted" data-read={t("emptyNote")}>{t("emptyNote")}</p>
        <button type="button" className="btn-green min-h-14 w-full text-[18px]" onClick={go} disabled={busy} data-testid="confirm">
          {t("confirmBtn")} <ArrowRight size={22} aria-hidden />
        </button>
      </div>
    </main>
  );
}
