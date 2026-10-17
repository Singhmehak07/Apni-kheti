import { useState } from "react";
import { CircleCheck, TriangleAlert, IndianRupee, CircleHelp, Info, ArrowRight, Star, ChevronDown } from "lucide-react";
import { useApp } from "../context.js";
import Icon, { CROP_TONE } from "./Icon.jsx";
import SpeakButton from "./SpeakButton.jsx";
import { num, rs } from "../lib/format.js";

const KIND = {
  fit: [CircleCheck, "text-green-ink"], caution: [TriangleAlert, "text-orange-ink"], money: [IndianRupee, "text-blue-ink"],
  data: [CircleHelp, "text-muted"], info: [Info, "text-muted"],
};
const STATUS = {
  feasible: "bg-green-soft text-green-ink", conditional: "bg-orange-soft text-orange-ink",
  insufficient_information: "bg-sunken text-ink", not_suitable: "bg-red-soft text-red-ink",
};

function Reason({ r }) {
  const [I, c] = KIND[r.kind || r.type] || KIND.info;
  return <li className="flex gap-2.5"><I size={19} className={`mt-[3px] shrink-0 ${c}`} aria-hidden /><span>{r.text}</span></li>;
}

export default function CropCard({ crop, why, best, usual, onChoose, busy }) {
  const { t } = useApp();
  const tone = CROP_TONE[crop.color] || CROP_TONE.green;
  const e = crop.economics || {};
  const n = e.net_rs_acre;
  const whyList = why?.reasons?.length ? why.reasons : crop.reasons.filter((r) => ["fit", "money", "caution"].includes(r.type)).slice(0, 4);
  const shown = new Set(whyList.map((r) => r.text));
  const extra = crop.reasons.filter((r) => ["caution", "data"].includes(r.type) && !shown.has(r.text));
  const headline = why?.headline || crop.headline;
  const money = n ? `${t("normalYear")}: ${rs(n.base)} ${t("perAcreShort")}. ${t("badYear")} ${rs(n.low)}, ${t("goodYear")} ${rs(n.high)}.` : "";
  const say = [crop.name, headline, money, ...whyList.map((r) => r.text), ...extra.map((r) => r.text)].join("। ");
  const off = crop.status === "not_suitable";
  const [open, setOpen] = useState(!!best);
  const firstCaution = whyList.find((r) => (r.kind || r.type) === "caution");
  return (
    <article className={`card overflow-hidden ${best ? "border-ink ring-1 ring-ink" : ""}`} data-testid={`crop-${crop.crop_id}`}>
      {best && <p className="flex items-center gap-1.5 bg-ink px-4 py-1.5 text-[14px] font-semibold text-white"><Star size={15} fill="currentColor" aria-hidden />{t("bestMatch")}</p>}
      <div className="space-y-4 p-4 sm:p-5">
        <header className="flex items-start gap-3">
          <span className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-[8px] ${tone.bg} ${tone.text}`}><Icon name={crop.crop_id} size={26} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[21px] font-bold leading-tight" data-read={crop.name}>{crop.name}</h3>
              <span className={`chip ${STATUS[crop.status]}`}>{t(`st_${crop.status}`)}</span>
              {usual && <span className="chip bg-sunken text-muted">{t("yourUsual")}</span>}
            </div>
            <p className="text-[15px] text-muted" data-read={headline}>{headline}</p>
          </div>
          <SpeakButton text={say} id={`crop-${crop.crop_id}`} label={crop.name} />
        </header>

        {n && !off && (
          <div className="rounded-[8px] bg-canvas p-3.5">
            <p className="flex flex-wrap items-baseline gap-x-2"><span className={`text-[28px] font-bold tabular-nums ${n.base < 0 ? "text-red-ink" : ""}`} data-testid="net-base">{rs(n.base)}</span><span className="text-[14px] text-muted">{t("perAcre")}</span></p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-[14px]">
              <p><span className="text-muted">{t("badYear")}</span> <b className="tabular-nums">{rs(n.low)}</b></p>
              <p className="text-right"><span className="text-muted">{t("goodYear")}</span> <b className="tabular-nums">{rs(n.high)}</b></p>
            </div>
            {e.net_total && <p className="mt-2 border-t border-line pt-2 text-[15px] font-semibold">{t("forFarm", { acres: num(e.acres), total: rs(e.net_total.base) })}</p>}
          </div>
        )}

        {!open && off && firstCaution && <ul className="text-[15px]"><Reason r={firstCaution} /></ul>}

        {open && (
          <>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[15px] sm:grid-cols-3">
              {crop.variety && <div><dt className="text-muted">{t("variety")}</dt><dd className="font-semibold">{crop.variety}</dd></div>}
              {crop.sow_date_label && <div><dt className="text-muted">{t("sowOn")}</dt><dd className="font-semibold">{crop.sow_date_label}</dd></div>}
              {crop.window_label && <div><dt className="text-muted">{t("bestTime")}</dt><dd className="font-semibold">{crop.window_label}</dd></div>}
            </dl>
            <div>
              <h4 className="mb-1.5 font-bold">{t("why")}</h4>
              <ul className="space-y-1.5" data-testid="reasons">{whyList.map((r, i) => <Reason key={i} r={r} />)}</ul>
              {extra.length > 0 && (
                <details className="mt-2 border-t border-line pt-1">
                  <summary className="flex min-h-11 cursor-pointer items-center text-[15px] font-semibold text-muted">{t("moreNotes", { n: extra.length })}</summary>
                  <ul className="space-y-1.5 pb-1 text-[15px]">{extra.map((r, i) => <Reason key={i} r={r} />)}</ul>
                </details>
              )}
            </div>
            {n && (
              <details className="rounded-[8px] border border-line">
                <summary className="flex min-h-11 cursor-pointer items-center px-3 text-[15px] font-semibold">{t("details")}</summary>
                <dl className="grid grid-cols-2 gap-2 px-3 pb-3 text-[14px] sm:grid-cols-4">
                  <div><dt className="text-muted">{t("yieldL")}</dt><dd className="font-semibold">{num(e.yield_q_acre?.low)}–{num(e.yield_q_acre?.high)} {t("qAcre")}</dd></div>
                  <div><dt className="text-muted">{t("priceL")}</dt><dd className="font-semibold">{rs(e.price_rs_q?.base)}{t("perQ")}</dd></div>
                  <div><dt className="text-muted">{t("costL")}</dt><dd className="font-semibold">{rs(e.cost_rs_acre)}{t("perAcreShort")}</dd></div>
                  {e.msp_rs_q && <div><dt className="text-muted">{t("mspL")}</dt><dd className="font-semibold">{rs(e.msp_rs_q)}{t("perQ")}</dd></div>}
                </dl>
              </details>
            )}
          </>
        )}

        <div className="flex flex-col gap-2 sm:flex-row">
          <button type="button" className="btn-ghost min-h-12 border border-line sm:w-auto" onClick={() => setOpen(!open)} aria-expanded={open} data-testid={`why-${crop.crop_id}`}>
            <ChevronDown size={18} className={`transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />{open ? t("hide") : t("whyMore")}
          </button>
        {!off && (
          <button type="button" className={`${best ? "btn-green" : "btn-secondary"} min-h-12 flex-1`} onClick={() => onChoose(crop.crop_id)} disabled={busy} data-testid={`choose-${crop.crop_id}`}>
            {t("chooseCrop", { crop: crop.name })} <ArrowRight size={20} aria-hidden />
          </button>
        )}
        </div>
      </div>
    </article>
  );
}
