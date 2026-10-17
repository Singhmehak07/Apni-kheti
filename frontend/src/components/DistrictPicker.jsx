import { useMemo, useState } from "react";
import { Search, MapPin } from "lucide-react";
import { useApp } from "../context.js";
import SpeakButton from "./SpeakButton.jsx";

export default function DistrictPicker({ options, onPick, disabled }) {
  const { t, lang } = useApp();
  const [q, setQ] = useState("");
  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    const sorted = [...options].sort((a, b) => a.label.localeCompare(b.label, lang));
    if (!s) return sorted;
    return sorted.filter((o) => `${o.label} ${o.sub || ""} ${o.id}`.toLowerCase().includes(s));
  }, [q, options, lang]);
  return (
    <div className="space-y-3">
      <label className="relative block">
        <span className="sr-only">{t("searchDistrict")}</span>
        <Search size={20} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
        <input className="field pl-11" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchDistrict")} data-testid="district-search" />
      </label>
      {list.length === 0 && <p className="text-muted">{t("noMatch")}</p>}
      <ul className="grid max-h-[380px] grid-cols-1 gap-2 overflow-y-auto pr-1 min-[420px]:grid-cols-2 sm:grid-cols-3" role="list">
        {list.map((o) => (
          <li key={o.id} className="card flex items-center hover:border-[#cfcdc9]">
            <button type="button" disabled={disabled} onClick={() => onPick(o)} data-testid={`opt-district-${o.id}`}
              className="flex min-h-14 flex-1 items-center gap-2.5 px-3 py-2 text-left">
              <MapPin size={20} className="shrink-0 text-muted" aria-hidden />
              <span className="min-w-0">
                <span className="block font-semibold leading-tight">{o.label}</span>
                {o.sub && <span className="block text-[13px] text-muted">{o.sub}</span>}
              </span>
            </button>
            <SpeakButton text={o.label} size="sm" tone="quiet" label={o.label} className="mr-1" />
          </li>
        ))}
      </ul>
    </div>
  );
}
