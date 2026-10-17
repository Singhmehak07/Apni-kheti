import { CloudRain, Sun, CloudSun } from "lucide-react";
import { useApp } from "../context.js";
import SpeakButton from "./SpeakButton.jsx";

export default function WeatherStrip({ weather }) {
  const { t } = useApp();
  if (!weather || weather.status !== "ok") return <p className="card px-4 py-3 text-muted" data-read={t("weatherNA")}>{t("weatherNA")}</p>;
  const days = weather.days || [];
  const lo = Math.min(...days.map((d) => d.tmin)), hi = Math.max(...days.map((d) => d.tmax));
  const rain = days.reduce((s, d) => s + (d.rain_mm || 0), 0);
  const say = `${t("weather7")}: ${Math.round(lo)}–${Math.round(hi)}°C. ${days.filter((d) => d.rain_mm >= 1).map((d) => `${d.date_label} ${Math.round(d.rain_mm)} mm`).join(", ")}`;
  return (
    <section className="card p-4" aria-label={t("weather7")} data-testid="weather">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="flex-1 font-bold" data-read={say}>{t("weather7")}</h2>
        <span className="text-[14px] text-muted">{Math.round(lo)}–{Math.round(hi)}°C{rain >= 1 ? ` · ${Math.round(rain)} mm` : ""}</span>
        <SpeakButton text={say} size="sm" tone="quiet" label={t("weather7")} />
      </div>
      <ol className="grid grid-cols-7 gap-1 text-center">
        {days.slice(0, 7).map((d) => {
          const wet = d.rain_mm >= 1 || d.rain_prob >= 60;
          const I = wet ? CloudRain : d.rain_prob >= 30 ? CloudSun : Sun;
          return (
            <li key={d.date} className={`rounded-[8px] px-0.5 py-2 ${wet ? "bg-blue-soft" : "bg-sunken"}`}>
              <p className="truncate text-[13px] font-semibold text-muted">{d.label}</p>
              <I size={20} className={`mx-auto my-1 ${wet ? "text-blue-ink" : "text-orange"}`} aria-hidden />
              <p className="text-[14px] font-bold">{Math.round(d.tmax)}°</p>
              <p className="text-[12px] text-muted">{wet ? `${Math.round(d.rain_mm)}mm` : `${Math.round(d.tmin)}°`}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
