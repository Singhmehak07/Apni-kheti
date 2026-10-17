import { useApp } from "../context.js";
import { CROP_TONE } from "./Icon.jsx";
import { rs } from "../lib/format.js";
import SpeakButton from "./SpeakButton.jsx";

/** Range chart: line = bad→good year, dot = normal year, per acre after costs. */
export default function CompareChart({ crops }) {
  const { t } = useApp();
  const rows = crops.filter((c) => c.economics?.net_rs_acre);
  if (!rows.length) return null;
  const vals = rows.flatMap((c) => [c.economics.net_rs_acre.low, c.economics.net_rs_acre.high]);
  const min = Math.min(0, ...vals), max = Math.max(...vals);
  const pos = (v) => ((v - min) / (max - min || 1)) * 100;
  const say = `${t("compareTitle")}. ` + rows.map((c) => `${c.name}: ${t("normalYear")} ${rs(c.economics.net_rs_acre.base)}`).join("। ");
  return (
    <section className="card p-4" data-testid="compare">
      <div className="mb-1 flex items-center gap-2">
        <h2 className="flex-1 font-bold" data-read={say}>{t("compareTitle")}</h2>
        <SpeakButton text={say} size="sm" tone="quiet" label={t("compareTitle")} />
      </div>
      <p className="mb-3 text-[14px] text-muted">{t("compareNote")}</p>
      <ul className="space-y-3" role="list">
        {rows.map((c) => {
          const n = c.economics.net_rs_acre, tone = CROP_TONE[c.color] || CROP_TONE.green;
          const dim = c.status === "not_suitable";
          return (
            <li key={c.crop_id} className={`grid grid-cols-[88px_1fr_auto] items-center gap-3 sm:grid-cols-[120px_1fr_auto] ${dim ? "opacity-55" : ""}`}>
              <span className="truncate text-[15px] font-semibold">{c.name}</span>
              <span className="relative h-7" aria-hidden>
                <span className="absolute inset-y-[13px] left-0 right-0 rounded bg-sunken" />
                {min < 0 && <span className="absolute inset-y-1 w-px bg-muted/50" style={{ left: `${pos(0)}%` }} />}
                <span className="absolute inset-y-[11px] rounded-full opacity-45" style={{ left: `${pos(n.low)}%`, width: `${pos(n.high) - pos(n.low)}%`, background: tone.hex }} />
                <span className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow" style={{ left: `${pos(n.base)}%`, background: tone.hex }} />
              </span>
              <span className={`text-right text-[15px] font-bold tabular-nums ${n.base < 0 ? "text-red-ink" : ""}`}>{rs(n.base)}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
