import { Check } from "lucide-react";
import { useApp } from "../context.js";

export default function Stepper({ index }) {
  const { t } = useApp();
  const steps = t("steps");
  return (
    <nav aria-label={t("stepOf", { n: index + 1 })} className="mx-auto max-w-3xl px-4 pt-4">
      <ol className="flex items-center gap-1.5">
        {steps.map((s, i) => {
          const state = i < index ? "done" : i === index ? "now" : "next";
          return (
            <li key={s} className="flex min-w-0 flex-1 flex-col gap-1.5" aria-current={state === "now" ? "step" : undefined}>
              <span className={`h-1.5 rounded-full ${state === "next" ? "bg-line" : state === "now" ? "bg-ink" : "bg-green"}`} />
              <span className={`flex items-center gap-1 truncate text-[13px] font-semibold ${state === "now" ? "text-ink" : "text-muted"} ${state === "now" ? "" : "max-sm:hidden"}`}>
                {state === "done" && <Check size={14} className="text-green-ink" aria-hidden />}
                {s}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
