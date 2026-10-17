import { FileText, MessageSquare, Calculator, CircleDashed, Keyboard } from "lucide-react";
import { useApp } from "../context.js";
const STYLE = {
  report: ["bg-green-soft text-green-ink", FileText],
  farmer: ["bg-blue-soft text-blue-ink", MessageSquare],
  derived: ["bg-sunken text-ink", Calculator],
  manual: ["bg-blue-soft text-blue-ink", Keyboard],
  not_available: ["bg-sunken text-muted", CircleDashed],
};
export default function Provenance({ kind }) {
  const { t } = useApp();
  const [cls, I] = STYLE[kind] || STYLE.not_available;
  return <span className={`chip ${cls}`}><I size={13} aria-hidden />{t(`prov_${kind}`)}</span>;
}
