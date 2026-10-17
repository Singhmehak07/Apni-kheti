import { CircleCheck, TriangleAlert, Info } from "lucide-react";
export default function Toast({ toast }) {
  if (!toast) return null;
  const tone = { ok: "bg-green-soft text-green-ink border-[#cfe3d7]", warn: "bg-orange-soft text-orange-ink border-[#f2d6bf]", info: "bg-blue-soft text-blue-ink border-[#cfe5f8]" }[toast.kind || "info"];
  const I = toast.kind === "ok" ? CircleCheck : toast.kind === "warn" ? TriangleAlert : Info;
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-40 flex justify-center px-4">
      <div key={toast.id} className={`anim-in pointer-events-auto flex max-w-md items-start gap-2 rounded-[8px] border px-4 py-3 text-[15px] font-semibold shadow-sm ${tone}`}>
        <I size={20} className="mt-0.5 shrink-0" aria-hidden /> <span>{toast.text}</span>
      </div>
    </div>
  );
}
