import { useRef, useState } from "react";
import { FileUp, LoaderCircle, CircleCheck, TriangleAlert, ArrowRight } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import SpeakButton from "./SpeakButton.jsx";

const KEY = ["ph", "ec", "oc"];

export function ReportSummary({ report }) {
  const { t } = useApp();
  if (!report?.params) return null;
  const p = report.params;
  const flags = report.flags || [];
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-3 gap-2">
        {KEY.map((k) => (
          <div key={k} className="rounded-[8px] bg-sunken px-3 py-2">
            <dt className="text-[13px] font-semibold text-muted">{k === "oc" ? t("ocLabel") : p[k]?.label || k.toUpperCase()}</dt>
            <dd className="text-[20px] font-bold">{p[k]?.value ?? "—"} <span className="text-[13px] font-normal text-muted">{p[k]?.unit}</span></dd>
          </div>
        ))}
      </dl>
      {flags.length ? flags.map((f) => (
        <p key={f} data-read={t(`flag_${f}`)} className="flex items-center gap-2 rounded-[8px] bg-orange-soft px-3 py-2 font-semibold text-orange-ink">
          <TriangleAlert size={18} aria-hidden /> {t(`flag_${f}`)}
        </p>
      )) : <p className="flex items-center gap-2 text-green-ink font-semibold" data-read={t("reportNormal")}><CircleCheck size={18} aria-hidden />{t("reportNormal")}</p>}
    </div>
  );
}

function ManualValues({ sid, onSaved }) {
  const { t } = useApp();
  const [v, setV] = useState({ ph: "", ec: "", oc: "" });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    const body = Object.fromEntries(Object.entries(v).filter(([, x]) => x !== "").map(([k, x]) => [k, parseFloat(x)]));
    try { onSaved(await api.patchReport(sid, body)); } finally { setBusy(false); }
  };
  const any = Object.values(v).some((x) => x !== "");
  return (
    <div className="space-y-2">
      <p className="font-semibold">{t("typeValues")}</p>
      <div className="grid grid-cols-3 gap-2">
        {[["ph", "pH"], ["ec", "EC (dS/m)"], ["oc", "OC (%)"]].map(([k, l]) => (
          <label key={k} className="block">
            <span className="text-[13px] font-semibold text-muted">{l}</span>
            <input className="field" inputMode="decimal" data-testid={`manual-${k}`} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value.replace(/[^0-9.]/g, "") })} />
          </label>
        ))}
      </div>
      <button type="button" className="btn-secondary" disabled={!any || busy} onClick={save} data-testid="manual-save">{t("save")}</button>
    </div>
  );
}

/** Upload a Soil Health Card (PDF or photo). PDFs are read from their text layer; photos need Gemini vision. */
export default function ReportUpload({ sid, report, onReport, onContinue, onSkip, compact = false, showManual = false }) {
  const { t } = useApp();
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const upload = async (file) => {
    if (!file) return;
    setBusy(true); setFailed(false);
    try {
      const r = await api.uploadReport(sid, file);
      if (r.status === "ok" && r.count > 0) onReport(r); else setFailed(true);
    } catch { setFailed(true); } finally { setBusy(false); if (input.current) input.current.value = ""; }
  };
  const ok = report?.params && Object.keys(report.params).length > 0;
  return (
    <section className={`card space-y-4 ${compact ? "p-4" : "p-5"}`} aria-live="polite">
      <div className="flex items-start gap-3">
        <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-[8px] bg-green-soft text-green-ink"><FileUp size={22} aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[19px] font-bold" data-read={t("uploadTitle")}>{t("uploadTitle")}</h2>
          <p className="text-muted" data-read={t("uploadHint")}>{t("uploadHint")}</p>
        </div>
        <SpeakButton text={`${t("uploadTitle")}। ${t("uploadHint")}`} label={t("uploadTitle")} />
      </div>
      <input ref={input} type="file" accept="application/pdf,image/*" className="sr-only" data-testid="report-file"
        onChange={(e) => upload(e.target.files?.[0])} />
      {!ok && (
        <button type="button" className={`${compact ? "btn-secondary min-h-12" : "btn-green min-h-14 text-[17px]"} w-full`} disabled={busy} onClick={() => input.current?.click()} data-testid="report-choose">
          {busy ? <><LoaderCircle className="animate-spin" size={20} aria-hidden />{t("reading")}</> : <><FileUp size={20} aria-hidden />{t("chooseFile")}</>}
        </button>
      )}
      {ok && (
        <>
          <p className="flex items-center gap-2 font-semibold text-green-ink" data-testid="report-ok" data-read={t("readOk", { n: report.count ?? Object.keys(report.params).length })}>
            <CircleCheck size={20} aria-hidden /> {report.method === "manual" ? t("prov_manual") : t("readOk", { n: report.count ?? Object.keys(report.params).length })}
          </p>
          <ReportSummary report={report} />
        </>
      )}
      {failed && <p className="rounded-[8px] bg-orange-soft px-3 py-2 font-semibold text-orange-ink" role="alert" data-read={t("unreadable")}>{t("unreadable")}</p>}
      {!ok && (failed || showManual) && <ManualValues sid={sid} onSaved={onReport} />}
      {(onContinue || onSkip) && (
        <div className="flex flex-wrap gap-2 pt-1">
          {ok && onContinue && <button type="button" className="btn-primary min-h-12 flex-1" onClick={onContinue} data-testid="report-continue">{t("continue")} <ArrowRight size={20} aria-hidden /></button>}
          {!ok && onSkip && <button type="button" className="btn-secondary min-h-12 flex-1" onClick={onSkip} data-testid="report-skip">{t("skipReport")}</button>}
        </div>
      )}
    </section>
  );
}
