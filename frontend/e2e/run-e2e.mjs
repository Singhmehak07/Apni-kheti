// End-to-end browser test: three languages, chips / typing / unclear re-asks / skip / report upload /
// results / plan / assistant / speak buttons, plus the voice path against mock Sarvam + Gemini.
import { chromium } from "playwright-core";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const BASE = process.env.BASE || "http://127.0.0.1:8000";
const VOICE_BASE = process.env.VOICE_BASE || "";
const MOCK = process.env.MOCK || "http://127.0.0.1:8099";
const SHOTS = process.env.SHOTS || path.join(ROOT, "docs/screenshots");
const ONLY = (process.env.ONLY || "pa,hi,en").split(",");
const EXE = process.env.CHROMIUM || "/usr/local/bin/chromium";
const SAMPLE = (n) => path.join(ROOT, "docs/samples", n);
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
const ok = (name) => { results.push(["PASS", name]); console.log("  ✓", name); };
function expect(cond, name) { if (!cond) throw new Error("FAILED: " + name); ok(name); }

const STUB = () => {
  window.__spoken = [];
  window.__played = [];
  const s = window.speechSynthesis;
  if (s) s.speak = (u) => { window.__spoken.push({ text: u.text, lang: u.lang }); setTimeout(() => u.onend && u.onend(), 20); };
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { window.__played.push(this.src); return play.call(this); };
};

async function newPage(browser, { width = 1280, height = 900, base = BASE } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height }, locale: "en-IN", permissions: ["microphone"] });
  await ctx.addInitScript(STUB);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource.*(404|503)/.test(m.text())) errors.push(m.text()); });
  page.base = base; page.errors = errors;
  return page;
}
const shot = async (page, name) => {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(450);   // let fade-in animations finish
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
};
const q = (page) => page.locator('[data-testid="question"]');
async function waitQ(page, re, label) {
  await page.waitForFunction(([src]) => new RegExp(src).test(document.querySelector('[data-testid="question"]')?.textContent || ""), [re.source], { timeout: 10000 });
  ok(label || `question: ${re.source}`);
}
const typeAnswer = async (page, text) => { await page.fill('[data-testid="type-answer"]', text); await page.click('[data-testid="type-answer-send"]'); };
const tap = (page, field, id) => page.click(`[data-testid="opt-${field}-${id}"]`);
const spoken = (page) => page.evaluate(() => window.__spoken.map((s) => s.text));

async function flowPunjabiDesktop(browser) {
  console.log("\n▶ Punjabi · desktop · typing, report upload, re-ask, back, skip");
  const page = await newPage(browser);
  await page.goto(page.base);
  await page.waitForSelector('[data-testid="start-pa"]');
  await shot(page, "01-welcome-desktop");
  await page.click('[data-testid="start-pa"]');
  await waitQ(page, /ਮਿੱਟੀ ਪਰਖ/, "first question: soil report");
  await page.waitForFunction(() => window.__spoken.some((s) => /ਮਿੱਟੀ/.test(s.text) && s.lang === "pa-IN"));
  ok("question auto-read aloud in pa-IN after first tap");
  await shot(page, "02-question-soil-report-desktop");

  await page.setInputFiles('[data-testid="report-file"]', SAMPLE("sample_soil_health_card_bathinda.pdf"));
  await waitQ(page, /ਜ਼ਿਲ੍ਹੇ/, "report uploaded → moved to district");
  expect(/12/.test(await page.textContent('[data-testid="ack"]')), "ack shows 12 values read from report");

  await typeAnswer(page, "ਬਠਿੰਡਾ ਵਿੱਚ 5 ਕਿੱਲੇ");
  await waitQ(page, /ਜ਼ਮੀਨ ਕਿਹੋ ਜਿਹੀ/, "one sentence filled district + land → soil type");
  const ack = await page.textContent('[data-testid="ack"]');
  expect(ack.includes("ਬਠਿੰਡਾ") && ack.includes("5"), "ack lists both district and land");

  await typeAnswer(page, "ਹਰੀ");
  await waitQ(page, /ਮਾਫ਼ ਕਰਨਾ/, "unclear answer → rephrased re-ask");
  await page.waitForFunction(() => window.__spoken.some((s) => /ਮਾਫ਼ ਕਰਨਾ/.test(s.text)));
  ok("re-ask is read aloud");
  await shot(page, "03-reask-desktop");
  await tap(page, "soil_type", "loam");
  await waitQ(page, /ਪਾਣੀ ਕਿੱਥੋਂ/);
  await page.locator('[data-testid="opt-water_source-tubewell"]').locator("xpath=..").getByTestId("speak").click();
  await page.waitForFunction(() => window.__spoken.some((s) => /ਟਿਊਬਵੈੱਲ/.test(s.text)));
  ok("option speaker reads the option label");
  await tap(page, "water_source", "tubewell");
  await waitQ(page, /ਮਿੱਠਾ ਹੈ ਜਾਂ ਖਾਰਾ/);
  await typeAnswer(page, "ਖਾਰਾ ਪਾਣੀ");
  await waitQ(page, /ਕਿੰਨੇ ਪਾਣੀ/);
  await tap(page, "irrigations", "1-2");
  await waitQ(page, /ਆਮ ਤੌਰ/);
  await tap(page, "usual_crop", "wheat");
  await waitQ(page, /ਸਾਉਣੀ/);
  await typeAnswer(page, "ਨਰਮਾ");
  await waitQ(page, /ਤਿਆਰ ਹੋਵੇਗਾ/);
  await tap(page, "field_ready", "late_oct");
  await waitQ(page, /ਟਰੈਕਟਰ/);
  await page.click('[data-testid="back"]');
  await waitQ(page, /ਤਿਆਰ ਹੋਵੇਗਾ/, "Back returns to the previous question");
  await tap(page, "field_ready", "late_oct");
  await waitQ(page, /ਟਰੈਕਟਰ/);
  await page.click('[data-testid="skip"]');
  await waitQ(page, /ਖ਼ਰਚ/, "'Don't know' skips to next question");
  expect(/ਖ਼ਾਲੀ/.test(await page.textContent('[data-testid="ack"]')), "skip acknowledged as left empty");
  await tap(page, "budget", "mid");

  await page.waitForSelector('[data-testid="profile"]');
  ok("confirm screen shown");
  expect((await page.textContent('[data-testid="row-tractor"]')).includes("ਨਹੀਂ ਦੱਸਿਆ"), "skipped tractor shows 'not given'");
  expect((await page.textContent('[data-testid="row-district"]')).includes("ਬਠਿੰਡਾ"), "district row correct");
  expect(/1\.12/.test(await page.textContent("main")), "report EC 1.12 shown on confirm");
  const before = await page.textContent('[data-testid="row-soil_type"]');
  await page.click('[data-testid="change-soil_type"]');
  await page.waitForSelector('[data-testid="editor-soil_type"] [data-testid="opt-soil_type-sandy"]');
  await page.click('[data-testid="editor-soil_type"] [data-testid="opt-soil_type-sandy"]');
  await page.waitForFunction((b) => document.querySelector('[data-testid="row-soil_type"]')?.textContent !== b, before);
  ok("editing a row on confirm updates it");
  await shot(page, "04-confirm-desktop");
  await page.click('[data-testid="confirm"]');

  await page.waitForSelector('[data-testid="crops"] article', { timeout: 20000 });
  const crops = await page.locator('article[data-testid^="crop-"]').count();
  expect(crops === 4, "4 crops evaluated");
  await page.waitForSelector('[data-testid="weather"]');
  ok("weather strip rendered");
  const raya = await page.textContent('[data-testid="crop-raya"]');
  expect(/EC 1\.12|ਲੂਣ/.test(raya), "raya card keeps the salty-soil caution in its reasons");
  await page.locator('article[data-testid^="crop-"]').first().getByTestId("speak").first().click();
  await page.waitForFunction(() => window.__spoken.some((s) => s.text.length > 80));
  ok("crop card read aloud");
  await page.click('[data-testid="read-screen"]');
  await page.waitForFunction(() => window.__spoken.some((s) => /ਮੌਸਮ/.test(s.text)));
  ok("Read this screen reads the results page");
  await shot(page, "05-results-desktop");

  const firstId = (await page.locator('article[data-testid^="crop-"]').first().getAttribute("data-testid")).replace("crop-", "");
  await page.click(`[data-testid="choose-${firstId}"]`);
  await page.waitForSelector('[data-testid="timeline"] li');
  const steps = await page.locator('[data-testid="timeline"] > li').count();
  expect(steps >= 6, `plan has ${steps} dated steps`);
  await page.fill('[data-testid="ask-input"]', "ਪਾਣੀ ਕਦੋਂ ਲਾਈਏ?");
  await page.click('[data-testid="ask-send"]');
  await page.waitForSelector('[data-testid="answer"]');
  expect((await page.textContent('[data-testid="answer"]')).length > 20, "assistant answered from the plan");
  await shot(page, "06-plan-desktop");
  await page.click('[data-testid="lang-en"]');
  await page.waitForFunction(() => /plan/i.test(document.querySelector("main h1")?.textContent || ""));
  ok("language switch re-renders the plan in English");
  expect(page.errors.length === 0, "no console/page errors (" + page.errors.join(" | ") + ")");
  await page.context().close();
}

async function flowHindiMobile(browser) {
  console.log("\n▶ Hindi · 390px · district search, bigha, stepper, 3-strike empty");
  const page = await newPage(browser, { width: 390, height: 844 });
  await page.goto(page.base);
  await page.waitForSelector('[data-testid="start-hi"]');
  await shot(page, "10-welcome-mobile");
  await page.click('[data-testid="start-hi"]');
  await waitQ(page, /मिट्टी/);
  await shot(page, "11-question-mobile-hi");
  await tap(page, "soil_report", "no");
  await waitQ(page, /ज़िले/);
  await page.fill('[data-testid="district-search"]', "लुधि");
  expect(await page.locator('[data-testid^="opt-district-"]').count() === 1, "district search narrows to one");
  await shot(page, "12-district-mobile-hi");
  await tap(page, "district", "ludhiana");
  await waitQ(page, /एकड़/);
  await typeAnswer(page, "दो बीघा");
  await waitQ(page, /बीघे/, "bigha → asks for killa/acre instead");
  await page.fill('[data-testid="land-amount"]', "2.5");
  await page.click('[data-testid="unit-killa"]');
  await shot(page, "13-land-mobile-hi");
  await page.click('[data-testid="land-next"]');
  await waitQ(page, /ज़मीन कैसी/);
  await tap(page, "soil_type", "loam");
  await tap(page, "water_source", "canal");
  await waitQ(page, /सिंचाई/, "canal → water-quality question skipped");
  await tap(page, "irrigations", "3-4");
  await tap(page, "usual_crop", "wheat");
  await waitQ(page, /खरीफ|ख़रीफ़/);
  await tap(page, "previous_crop", "paddy");
  await tap(page, "field_ready", "nov_1h");
  await tap(page, "tractor", "own");
  await waitQ(page, /खर्च/);
  for (let i = 0; i < 3; i++) { await typeAnswer(page, "हम्म"); await page.waitForTimeout(250); }
  await page.waitForSelector('[data-testid="profile"]');
  ok("3 unclear answers → field left empty, interview finished");
  expect((await page.textContent('[data-testid="row-budget"]')).includes("नहीं बताया"), "budget row empty");
  await shot(page, "14-confirm-mobile-hi");
  await page.click('[data-testid="confirm"]');
  await page.waitForSelector('[data-testid="crops"] article', { timeout: 20000 });
  const firstId = (await page.locator('article[data-testid^="crop-"]').first().getAttribute("data-testid")).replace("crop-", "");
  expect(firstId === "wheat", "wheat ranks first for canal-irrigated Ludhiana after paddy");
  await shot(page, "15-results-mobile-hi");
  await page.click('[data-testid="choose-wheat"]');
  await page.waitForSelector('[data-testid="timeline"] li');
  expect(/धान के बाद/.test(await page.textContent('[data-testid="timeline"]')), "after-paddy variant in plan");
  await shot(page, "16-plan-mobile-hi");
  expect(page.errors.length === 0, "no console/page errors (" + page.errors.join(" | ") + ")");
  await page.context().close();
}

async function flowEnglishVoice() {
  if (!VOICE_BASE) { console.log("\n(skip voice flow: VOICE_BASE not set)"); return; }
  console.log("\n▶ English · voice via mock Sarvam STT/TTS + Gemini (WAV + VAD auto-stop)");
  const mock = (p, body) => fetch(MOCK + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  await mock("/__mock/reset");
  await mock("/__mock/stt-queue", { items: ["no I don't have it", "I farm 4 acres in Moga"] });
  const browser = await chromium.launch({
    executablePath: EXE,
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${path.join(HERE, "fake-speech.wav")}%noloop`, "--autoplay-policy=no-user-gesture-required"],
  });
  const page = await newPage(browser, { base: VOICE_BASE });
  try { await voiceSteps(page, mock); } catch (e) {
    await page.screenshot({ path: path.join(SHOTS, "zz-failure-voice.png"), fullPage: true }).catch(() => {});
    await browser.close(); throw e;
  }
  await browser.close();
}

async function voiceSteps(page, mock) {
  const ttsAudio = [];
  page.on("request", (r) => { if (r.url().includes("/api/v1/tts/audio/")) ttsAudio.push(r.url()); });
  await page.goto(page.base + "/?debug=1");
  await page.click('[data-testid="start-en"]');
  await waitQ(page, /soil test report/i);
  await page.waitForSelector('[data-testid="mic"]');
  ok("mic shown (server STT configured)");
  await page.click('[data-testid="mic"]');
  await page.waitForSelector('[data-testid="heard"]', { timeout: 15000 });
  ok("VAD auto-stopped after the pause and uploaded WAV");
  expect((await page.textContent('[data-testid="heard"]')).includes("no I don't have it"), "'We heard' shows the transcript");
  await waitQ(page, /district/i);
  await page.click('[data-testid="mic"]');
  await waitQ(page, /What kind of soil|soil/i, "spoken sentence filled district + land");
  const ack = await page.textContent('[data-testid="ack"]');
  expect(ack.includes("Moga") && ack.includes("4"), "ack shows Moga and 4 acres");
  const log = await (await fetch(MOCK + "/__mock/log")).json();
  const stt = log.filter((l) => l.api === "sarvam_stt");
  expect(stt.length === 2 && stt.every((l) => l.seconds > 0.8 && l.seconds < 6 && l.model === "saaras:v4"), `WAV sent to Sarvam saaras:v4 (${stt.map((l) => l.seconds + "s").join(", ")})`);
  await page.click('[data-testid="fix"]');
  await page.fill('[data-testid="fix-input"]', "Sangrur");
  await page.press('[data-testid="fix-input"]', "Enter");
  await page.waitForFunction(() => /Sangrur/.test(document.querySelector('[data-testid="ack"]')?.textContent || ""));
  ok("'Fix' corrects the heard answer (district → Sangrur)");
  await shot(page, "21-voice-heard-desktop-en");
  await page.waitForFunction(() => window.__played.some((u) => u.includes("/api/v1/tts/audio/")));
  ok("questions read with server TTS mp3 (Sarvam contract)");
  await tap(page, "soil_type", "loam");
  await tap(page, "water_source", "canal");
  await tap(page, "irrigations", "3-4");
  await tap(page, "usual_crop", "wheat");
  await tap(page, "previous_crop", "paddy");
  await tap(page, "field_ready", "nov_1h");
  await tap(page, "tractor", "own");
  await tap(page, "budget", "mid");
  await page.waitForSelector('[data-testid="profile"]');
  expect((await page.textContent('[data-testid="row-district"]')).includes("Sangrur"), "confirm shows corrected district");
  await page.click('[data-testid="confirm"]');
  await page.waitForSelector('[data-testid="crops"] article', { timeout: 20000 });
  await page.waitForTimeout(800);
  const txt = await page.textContent('[data-testid="crops"]');
  expect(!/99 quintal/.test(txt), "LLM 'why' reasons shown; hallucinated number dropped by guard");
  const llmCalls = (await (await fetch(MOCK + "/__mock/log")).json()).filter((l) => l.api === "gemini");
  expect(llmCalls.length >= 1, "explain used Gemini structured output");
  await page.click('[data-testid="debug-toggle"]');
  await page.waitForSelector('[data-testid="debug"] tr');
  ok("debug panel shows timings");
  await shot(page, "22-results-voice-debug-desktop-en");
  expect(page.errors.length === 0, "no console/page errors (" + page.errors.join(" | ") + ")");
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, args: ["--autoplay-policy=no-user-gesture-required"] });
  let failed = null;
  try {
    if (ONLY.includes("pa")) await flowPunjabiDesktop(browser);
    if (ONLY.includes("hi")) await flowHindiMobile(browser);
    if (ONLY.includes("en")) await flowEnglishVoice();
  } catch (e) {
    failed = e;
    console.error("\n✗", e.message.split("\n")[0]);
    for (const c of browser.contexts()) for (const p of c.pages()) await p.screenshot({ path: path.join(SHOTS, "zz-failure.png"), fullPage: true }).catch(() => {});
  }
  await browser.close();
  console.log(`\n${results.length} checks passed${failed ? ", 1 failed" : ""}`);
  process.exit(failed ? 1 : 0);
})();
