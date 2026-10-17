import { useState } from "react";
import { Minus, Plus, ArrowRight } from "lucide-react";
import { useApp } from "../context.js";

const QUICK = [1, 2, 5, 10];

export default function LandInput({ units, onSubmit, disabled, initial }) {
  const { t } = useApp();
  const [amount, setAmount] = useState(initial?.amount ?? "");
  const [unit, setUnit] = useState(initial?.unit || units?.[0]?.id || "killa");
  const n = parseFloat(amount);
  const valid = Number.isFinite(n) && n > 0;
  const step = unit === "kanal" ? 1 : 0.5;
  const bump = (d) => setAmount((a) => {
    const v = Math.max(0, (parseFloat(a) || 0) + d);
    return String(Math.round(v * 2) / 2);
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button type="button" className="btn-secondary h-14 w-14 shrink-0 p-0" onClick={() => bump(-step)} aria-label={t("less")} disabled={disabled}><Minus size={24} aria-hidden /></button>
        <label className="flex-1">
          <span className="sr-only">{t("amount")}</span>
          <input data-testid="land-amount" inputMode="decimal" className="field h-14 text-center text-[26px] font-bold" value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))} placeholder="0" />
        </label>
        <button type="button" className="btn-secondary h-14 w-14 shrink-0 p-0" onClick={() => bump(step)} aria-label={t("more")} disabled={disabled}><Plus size={24} aria-hidden /></button>
      </div>
      <div className="flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button key={q} type="button" onClick={() => setAmount(String(q))}
            className={`btn min-w-14 border ${String(q) === amount ? "border-ink bg-ink text-white" : "border-line bg-white"}`}>{q}</button>
        ))}
      </div>
      <div role="radiogroup" aria-label={t("unit")} className="grid grid-cols-3 gap-2">
        {units.map((u) => (
          <button key={u.id} type="button" role="radio" aria-checked={unit === u.id} onClick={() => setUnit(u.id)} data-testid={`unit-${u.id}`}
            className={`btn border px-2 text-[15px] ${unit === u.id ? "border-ink bg-ink text-white" : "border-line bg-white"}`}>{u.label}</button>
        ))}
      </div>
      <button type="button" className="btn-primary w-full min-h-12" disabled={!valid || disabled} data-testid="land-next"
        onClick={() => onSubmit({ amount: n, unit })}>
        {t("next")} <ArrowRight size={20} aria-hidden />
      </button>
    </div>
  );
}
