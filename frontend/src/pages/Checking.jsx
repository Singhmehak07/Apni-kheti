import { useEffect, useRef, useState } from "react";
import { CircleCheck, LoaderCircle, Circle, CloudSun, Store, Scale, TriangleAlert } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import Stepper from "../components/Stepper.jsx";
import SpeakButton from "../components/SpeakButton.jsx";

export default function Checking({ sid, onRec }) {
  const { t, lang } = useApp();
  const [st, setSt] = useState({ weather: "active", market: "active", crops: "wait" });
  const [err, setErr] = useState(false);
  const started = useRef(false);
  const run = async () => {
    setErr(false); setSt({ weather: "active", market: "active", crops: "wait" });
    try {
      const ctx = await api.context(sid);   // usually already prefetched once the district was known
      setSt({ weather: ctx.weather?.status === "ok" ? "done" : "na", market: "done", crops: "active" });
      const rec = await api.recommend(sid, lang);
      setSt((s) => ({ ...s, crops: "done" }));
      setTimeout(() => onRec(rec), 350);
    } catch { setErr(true); }
  };
  useEffect(() => { if (!started.current) { started.current = true; run(); } }, []); // eslint-disable-line
  const rows = [["weather", CloudSun, t("chkWeather")], ["market", Store, t("chkMarket")], ["crops", Scale, t("chkCrops")]];
  return (
    <main className="pb-24">
      <Stepper index={2} />
      <div className="mx-auto max-w-xl space-y-5 px-4 pt-8">
        <div className="flex items-start gap-3">
          <h1 className="flex-1 text-[26px] font-bold" data-read={t("checkingTitle")}>{t("checkingTitle")}</h1>
          <SpeakButton text={t("checkingTitle")} />
        </div>
        <ol className="card divide-y divide-line" data-testid="checking">
          {rows.map(([k, I, label]) => {
            const s = st[k];
            return (
              <li key={k} className="flex items-center gap-3 px-4 py-4" data-read={label}>
                <I size={22} className="text-muted" aria-hidden />
                <span className={`flex-1 font-semibold ${s === "wait" ? "text-muted" : ""}`}>{label}</span>
                {s === "done" ? <CircleCheck className="text-green" aria-label="done" />
                  : s === "na" ? <TriangleAlert className="text-orange" aria-label="not available" />
                  : s === "active" ? <LoaderCircle className="animate-spin text-blue" aria-label="working" />
                  : <Circle className="text-line" aria-hidden />}
              </li>
            );
          })}
        </ol>
        {err && (
          <div className="space-y-3" role="alert">
            <p className="font-semibold text-red-ink">{t("error")}</p>
            <button type="button" className="btn-primary" onClick={run}>{t("retry")}</button>
          </div>
        )}
      </div>
    </main>
  );
}
