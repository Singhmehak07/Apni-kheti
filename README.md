# Apni Kheti (Khet Saathi)

A Punjabi-first, voice-enabled **rabi crop and income planner** for small farmers.
It works in Punjabi, Hindi and English. Every screen can be read aloud, and every answer can be spoken, tapped or typed.

> Theme: Agriculture & Rural Development. This is a prototype. The ML model is left for later: `ML_ENABLED=false`, and recommendations are rules-only (`ml_status="skipped"`).

## Workflow
1. **Farmer input.** Upload a soil health card (PDF/photo) and/or answer questions by voice or text.
2. **Extract, validate and confirm.** One question at a time. Unclear answers are asked again (max 2 re-asks). "Don't know" leaves the field empty. A Confirm screen lets the farmer change any answer.
3. **Weather and market.** Open-Meteo forecast plus mandi prices (a dated snapshot when the live API is unavailable).
4. **Evaluate crops.** A rules engine (PAU Package of Practices) checks wheat, mustard, gram and barley for fit, cautions and blockers.
5. **Compare returns.** Low/base/high profit per acre and for the whole farm, with MSP as the benchmark.
6. **Farmer chooses.** Crop cards explain "why this crop" (LLM-structured reasons with a template fallback).
7. **Growing guidance.** A dated timeline (sowing → irrigation → harvest) that can be read aloud, plus follow-up questions by text or voice.

Questions asked: soil report, district, land area, soil type, water source, water quality, number of irrigations, usual crop, previous crop, field readiness, tractor access and budget.

## Quick start
```bash
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
cd backend && uvicorn main:app --port 8000
# open http://127.0.0.1:8000   (add ?debug=1 for the latency/provider panel)
```
No keys are needed. Without keys the app uses browser speech recognition and speech synthesis, a deterministic parser and template reasons.
Copy `.env.example` to `.env` and add `SARVAM_API_KEY` / `GEMINI_API_KEY` to turn on server voice and LLM reasons.

**Dev mode:** run `cd frontend && npm run dev` (Vite on :5173, which proxies `/api` to :8000).
**Pin the date for demos:** `APP_TODAY=2026-10-17 uvicorn main:app`.

## Providers (auto-selected from the keys you set)
| Job | With keys | Without keys |
|---|---|---|
| Speech to text | Sarvam **Saaras v4** (Gemini as a fallback) | Browser SpeechRecognition |
| Text to speech | Sarvam **Bulbul v3** (disk-cached mp3) | Browser speechSynthesis |
| Understanding answers | Deterministic parser first, Gemini 3.5 Flash-Lite only when the answer is unclear | Deterministic parser |
| "Why this crop" | Gemini structured reasons (guarded against made-up facts) | Template reasons |
| Report photos | Gemini vision | PDFs are parsed offline; photos need a key |

## Tests
```bash
cd backend && python3 -m pytest -q            # 70 tests
# End-to-end tests (Playwright + Chromium): app on :8000, mock providers on :8099, voice app on :8001
cd backend && uvicorn tests.mock_providers:app --port 8099 &
cd backend && SARVAM_API_KEY=test GEMINI_API_KEY=test SARVAM_BASE_URL=http://127.0.0.1:8099 \
  GEMINI_BASE_URL=http://127.0.0.1:8099 DB_PATH=/tmp/voice.db CACHE_DIR=/tmp/voicecache \
  uvicorn main:app --port 8001 &
cd frontend && VOICE_BASE=http://127.0.0.1:8001 CHROMIUM=/path/to/chromium node e2e/run-e2e.mjs   # 63 checks
```
The E2E suite runs three flows: Punjabi on desktop (report upload), Hindi on a 390 px phone (re-asks and "don't know"), and English by voice through the mock Sarvam/Gemini APIs. Screenshots are saved to `docs/screenshots/`.
Sample soil cards: `docs/samples/*.pdf` (Bathinda saline and Ludhiana normal).

## API (prefix `/api/v1`)
- **Sessions and questions:** `sessions`, `questions`, `conversation/{sid}/answer`, `answer-audio`, `back`, `question/{field}`
- **Reports and profile:** `reports/{sid}`, `profile/{sid}` (+ `/confirm`)
- **Context:** `context/{sid}` (+ `/prefetch`)
- **Recommendations:** `recommendations` (+ `/{rid}/explain`)
- **Plans and assistant:** `plans`, `assistant` (+ `/audio`)
- **Speech:** `tts`, `tts/prefetch`, `stt`
- **Meta:** `config`, `health`

## Layout
```
backend/   FastAPI app: routers/, services/ (flow, rules, economics, plan, explain, stt, tts, report), integrations/, knowledge/*.json, tests/
frontend/  React + Vite + Tailwind v4: pages/, components/, lib/ (speech, recorder), i18n/strings.js, e2e/
docs/      research-ui-tech-latency.md, samples/, screenshots/
ml/        placeholder for the later ML model
```

## Known limits
- Real Sarvam/Gemini latency hasn't been measured yet. Only the API contracts were tested, against mocks.
- Desktop browsers may not have a Punjabi voice. Use the Sarvam key for reliable Punjabi speech.
- Market prices are a dated snapshot (2026-10-09), because data.gov.in/Agmarknet were unreachable. Gram and barley use the MSP benchmark.
- Every figure is an estimate. Farmers should check with the local KVK/agriculture officer.
