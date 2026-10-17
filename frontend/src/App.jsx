import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { api } from "./api/client.js";
import { AppCtx } from "./context.js";
import { makeT } from "./i18n/strings.js";
import { setTtsProvider, stop } from "./lib/speech.js";
import Header from "./components/Header.jsx";
import Toast from "./components/Toast.jsx";
import DebugPanel from "./components/DebugPanel.jsx";
import Welcome from "./pages/Welcome.jsx";
import Interview from "./pages/Interview.jsx";
import Confirm from "./pages/Confirm.jsx";
import Checking from "./pages/Checking.jsx";
import Results from "./pages/Results.jsx";
import Plan from "./pages/Plan.jsx";

const DEBUG = new URLSearchParams(location.search).get("debug") === "1";
const saved = (() => { try { return JSON.parse(sessionStorage.getItem("ak_state") || "null"); } catch { return null; } })();

export default function App() {
  const [lang, setLangState] = useState(localStorage.getItem("ak_lang") || "pa");
  const [config, setConfig] = useState(null);
  const [cfgError, setCfgError] = useState(false);
  const [page, setPage] = useState("welcome");
  const [sid, setSid] = useState(null);
  const [question, setQuestion] = useState(null);
  const [report, setReport] = useState(null);
  const [rec, setRec] = useState(null);
  const [plan, setPlan] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const autoRead = true;
  const interacted = useRef(false);
  const t = useMemo(() => makeT(lang), [lang]);

  const loadConfig = useCallback(() => {
    setCfgError(false);
    api.config().then((c) => { setConfig(c); setTtsProvider(c.tts_provider); }).catch(() => setCfgError(true));
  }, []);
  useEffect(loadConfig, [loadConfig]);
  useEffect(() => {
    const mark = () => { interacted.current = true; };
    window.addEventListener("pointerdown", mark, { once: true, capture: true });
    window.addEventListener("keydown", mark, { once: true, capture: true });
  }, []);
  useEffect(() => { document.documentElement.lang = lang; localStorage.setItem("ak_lang", lang); }, [lang]);
  useEffect(() => { window.scrollTo({ top: 0 }); stop(); }, [page]);
  useEffect(() => {
    if (sid) sessionStorage.setItem("ak_state", JSON.stringify({ sid, page: page === "checking" ? "confirm" : page, recId: rec?.id, planId: plan?.id }));
  }, [sid, page, rec?.id, plan?.id]);

  const notify = useCallback((text, kind = "info") => {
    const id = Date.now();
    setToast({ text, kind, id });
    setTimeout(() => setToast((x) => (x?.id === id ? null : x)), 4200);
  }, []);

  const prefetchVoice = useCallback(async (l) => {
    if (!config || config.tts_provider === "browser") return;
    try { const q = await api.questions(l); api.ttsPrefetch(q.texts, l).catch(() => {}); } catch { /* optional */ }
  }, [config]);

  const setLang = async (l) => {
    if (l === lang) return;
    stop();
    setLangState(l);
    prefetchVoice(l);
    try {
      if (sid) {
        const r = await api.setLang(sid, l);
        if (page === "interview" && r.question) setQuestion(r.question);
      }
      if (rec && (page === "results" || page === "plan")) setRec(await api.recommendation(rec.id, l));
      if (plan && page === "plan") setPlan(await api.getPlan(plan.id, l));
    } catch { notify(makeT(l)("error"), "warn"); }
  };

  const start = async (l) => {
    setBusy(true);
    setLangState(l);
    try {
      const r = await api.newSession(l);
      setSid(r.session_id); setQuestion(r.question); setReport(null); setRec(null); setPlan(null);
      setPage("interview");
      prefetchVoice(l);
    } catch { notify(makeT(l)("offline"), "warn"); } finally { setBusy(false); }
  };

  const resume = async () => {
    if (!saved?.sid) return;
    setBusy(true);
    try {
      const s = await api.session(saved.sid, lang);
      setSid(saved.sid); setReport(s.profile?.report || null);
      if (saved.planId && saved.page === "plan") { setRec(saved.recId ? await api.recommendation(saved.recId, lang) : null); setPlan(await api.getPlan(saved.planId, lang)); setPage("plan"); }
      else if (saved.recId && saved.page === "results") { setRec(await api.recommendation(saved.recId, lang)); setPage("results"); }
      else if (s.done) setPage("confirm");
      else { setQuestion(s.question); setPage("interview"); }
    } catch { sessionStorage.removeItem("ak_state"); notify(t("error"), "warn"); } finally { setBusy(false); }
  };

  const choose = async (cropId) => {
    const p = await api.plan(rec.id, cropId, lang);
    setPlan(p); setPage("plan");
  };

  const restart = () => { sessionStorage.removeItem("ak_state"); setSid(null); setRec(null); setPlan(null); setReport(null); setPage("welcome"); };

  const ctx = { lang, setLang, t, config, notify, autoRead, interacted };

  return (
    <AppCtx.Provider value={ctx}>
      <div className="min-h-screen">
        <Header onHome={() => setPage("welcome")} />
        {cfgError ? (
          <main className="mx-auto max-w-xl space-y-3 px-4 py-16 text-center" role="alert">
            <p className="text-[18px] font-semibold">{t("offline")}</p>
            <button type="button" className="btn-primary" onClick={loadConfig}>{t("retry")}</button>
          </main>
        ) : !config ? (
          <main className="flex justify-center py-24"><LoaderCircle className="animate-spin text-muted" aria-label="loading" /></main>
        ) : page === "welcome" ? (
          <Welcome onStart={start} busy={busy} canResume={!!saved?.sid && !sid} onResume={resume} />
        ) : page === "interview" ? (
          <Interview sid={sid} question={question} setQuestion={setQuestion} report={report} setReport={setReport}
            onDone={() => setPage("confirm")} onExit={() => setPage("welcome")} />
        ) : page === "confirm" ? (
          <Confirm sid={sid} report={report} setReport={setReport} onConfirmed={() => setPage("checking")} />
        ) : page === "checking" ? (
          <Checking sid={sid} onRec={(r) => { setRec(r); setPage("results"); }} />
        ) : page === "results" && rec ? (
          <Results rec={rec} onChoose={choose} onEdit={() => setPage("confirm")} />
        ) : page === "plan" && plan ? (
          <Plan plan={plan} onBack={() => (rec ? setPage("results") : setPage("confirm"))} onRestart={restart} />
        ) : null}
        <Toast toast={toast} />
        {DEBUG && <DebugPanel config={config} />}
      </div>
    </AppCtx.Provider>
  );
}
