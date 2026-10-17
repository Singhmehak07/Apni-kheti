import { useEffect, useState } from "react";
import { apiLog, onApiLog } from "../api/client.js";

/** ?debug=1 — providers, models and per-call latency (client round trip + server spans). */
export default function DebugPanel({ config }) {
  const [log, setLog] = useState(apiLog());
  const [open, setOpen] = useState(false);
  useEffect(() => onApiLog((l) => setLog([...l])), []);
  return (
    <aside className={`fixed bottom-3 right-3 z-50 rounded-[8px] ${open ? "w-[min(440px,calc(100vw-24px))]" : "w-auto"}`+" border border-line bg-white text-[12px] shadow-lg"} data-testid="debug">
      <button type="button" data-testid="debug-toggle" className="flex w-full items-center justify-between gap-3 px-3 py-2 font-bold" onClick={() => setOpen(!open)}>
        <span>Debug · {log[0] ? `${log[0].ms}ms` : "timings"}</span><span>{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="max-h-[50vh] overflow-auto border-t border-line px-3 py-2 font-mono">
          {config && <p className="mb-2 whitespace-pre-wrap break-words text-muted">
            stt={config.stt_provider}{config.stt_model ? `(${config.stt_model})` : ""} tts={config.tts_provider}{config.tts_model ? `(${config.tts_model})` : ""} llm={config.llm?.enabled ? config.llm.model : "off"} market={config.market} ml={config.ml_status} engine={config.engine} today={config.today}
          </p>}
          <table className="w-full">
            <tbody>
              {log.map((e, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="py-1 pr-2">{e.method} {e.path.replace(/(ses|rec|plan)_[0-9a-f]+/g, ":id")}</td>
                  <td className="py-1 pr-2 text-right font-bold">{e.ms}ms</td>
                  <td className="py-1 text-muted">{e.status !== 200 ? e.status + " " : ""}{e.server ? Object.entries(e.server).map(([k, v]) => `${k}:${v}`).join(" ") : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </aside>
  );
}
