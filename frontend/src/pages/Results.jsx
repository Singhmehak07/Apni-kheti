import { useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { api } from "../api/client.js";
import { useApp } from "../context.js";
import Stepper from "../components/Stepper.jsx";
import WeatherStrip from "../components/WeatherStrip.jsx";
import CompareChart from "../components/CompareChart.jsx";
import CropCard from "../components/CropCard.jsx";
import SpeakButton from "../components/SpeakButton.jsx";

export default function Results({ rec, onChoose, onEdit }) {
  const { t, lang, notify } = useApp();
  const [why, setWhy] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {      // upgrade reasons with the LLM-structured "why" (template fallback is instant)
    let live = true;
    api.explain(rec.id, lang).then((ex) => {
      if (live) setWhy(Object.fromEntries(ex.crops.map((c) => [c.crop_id, { ...c, source: ex.source }])));
    }).catch(() => {});
    return () => { live = false; };
  }, [rec.id, lang]);
  const ok = rec.crops.filter((c) => c.status !== "not_suitable");
  const off = rec.crops.filter((c) => c.status === "not_suitable");
  const choose = async (id) => { setBusy(true); try { await onChoose(id); } catch { notify(t("error"), "warn"); } finally { setBusy(false); } };
  const top = ok[0];
  const intro = top ? `${t("resultsTitle")}. ${t("bestMatch")}: ${top.name}. ${why[top.crop_id]?.headline || top.headline}` : t("resultsTitle");
  return (
    <main className="pb-24">
      <Stepper index={3} />
      <div className="mx-auto max-w-3xl space-y-4 px-4 pt-5">
        <div className="flex items-start gap-3">
          <h1 className="flex-1 text-[26px] font-bold" data-read={intro}>{t("resultsTitle")}</h1>
          <SpeakButton text={intro} size="lg" label={t("resultsTitle")} />
        </div>
        <WeatherStrip weather={rec.weather} />
        <CompareChart crops={rec.crops} />
        <div className="space-y-4" data-testid="crops">
          {ok.map((c, i) => (
            <CropCard key={c.crop_id} crop={c} why={why[c.crop_id]} best={i === 0 && c.status === "feasible"} usual={c.crop_id === rec.usual_crop} onChoose={choose} busy={busy} />
          ))}
        </div>
        {off.length > 0 && (
          <section className="space-y-3 pt-2">
            <h2 className="text-[19px] font-bold" data-read={t("notNow")}>{t("notNow")}</h2>
            {off.map((c) => <CropCard key={c.crop_id} crop={c} why={why[c.crop_id]} usual={c.crop_id === rec.usual_crop} onChoose={choose} />)}
          </section>
        )}
        <p className="rounded-[8px] bg-sunken px-4 py-3 text-[15px] text-muted" data-read={t("estimateNote")}>{t("estimateNote")}</p>
        <details className="text-[14px] text-muted">
          <summary className="cursor-pointer py-2 font-semibold">{t("sources")}</summary>
          <ul className="list-disc space-y-1 pl-5">
            {[...new Map(rec.crops.flatMap((c) => c.sources || []).map((s) => [s.id, s])).values()].map((s) => (
              <li key={s.id}><a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.title}</a> — {s.publisher}</li>
            ))}
            {rec.weather?.status === "ok" && <li>Open-Meteo forecast, {rec.weather.fetched_at}</li>}
          </ul>
        </details>
        <button type="button" className="btn-secondary" onClick={onEdit} data-testid="edit-answers"><Pencil size={18} aria-hidden />{t("changeAnswers")}</button>
      </div>
    </main>
  );
}
