// Mic → 16 kHz mono 16-bit WAV with a simple energy VAD (auto-stop after a pause).
export function micSupported() {
  return !!(navigator.mediaDevices?.getUserMedia && (window.AudioContext || window.webkitAudioContext));
}

function encodeWav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

function downsample(input, from, to) {
  if (from === to) return input;
  const ratio = from / to;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const s = Math.floor(i * ratio), e = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0; for (let j = s; j < e; j++) sum += input[j];
    out[i] = sum / Math.max(1, e - s);
  }
  return out;
}

/**
 * Start recording. Returns { stop(), done: Promise<{blob, reason, speech, ms}> }.
 * reason: "silence" | "manual" | "max" | "no_speech"
 */
export function startRecording({ maxMs = 25000, silenceMs = 850, noSpeechMs = 7000, onLevel } = {}) {
  let finish = () => {};
  const done = (async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    await ctx.resume();
    const rate = ctx.sampleRate;
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(2048, 1, 1);

    // Mute gain node prevents mic input from feeding back into laptop speakers
    const mute = ctx.createGain();
    mute.gain.value = 0;
    proc.connect(mute);
    mute.connect(ctx.destination);
    src.connect(proc);

    const chunks = [];
    let total = 0, voiceEnd = 0, speech = false, lastVoice = 0;
    let noiseFloor = 0.008;
    let speechFrames = 0;
    const calib = [];
    const t0 = performance.now();

    return await new Promise((resolve) => {
      let ended = false;
      finish = (reason) => {
        if (ended) return; ended = true;
        try { proc.disconnect(); src.disconnect(); mute.disconnect(); } catch { /* ignore */ }
        stream.getTracks().forEach((t) => t.stop());
        ctx.close().catch(() => {});
        let len = total;
        if (speech) len = Math.min(total, voiceEnd + Math.round(0.35 * rate));  // trim trailing silence
        const pcm = new Float32Array(len);
        let off = 0;
        for (const c of chunks) { if (off >= len) break; pcm.set(c.subarray(0, Math.min(c.length, len - off)), off); off += c.length; }
        resolve({ blob: encodeWav(downsample(pcm, rate, 16000), 16000), reason, speech, ms: Math.round(performance.now() - t0) });
      };

      proc.onaudioprocess = (e) => {
        if (ended) return;
        const d = e.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(d));
        total += d.length;

        let sq = 0;
        for (let i = 0; i < d.length; i++) sq += d[i] * d[i];
        const rms = Math.sqrt(sq / d.length);
        const now = performance.now() - t0;

        onLevel?.(Math.min(1, Math.max(0, (rms - noiseFloor) / 0.10)));

        // Measure ambient room background noise floor in first 300ms
        if (now < 300) {
          calib.push(rms);
          return;
        }
        if (calib.length && noiseFloor === 0.008) {
          calib.sort((a, b) => a - b);
          noiseFloor = Math.max(0.003, calib[Math.floor(calib.length / 2)] || 0.008);
          calib.length = 0;
        }

        // Dual-threshold hysteresis VAD
        const speechThr = Math.max(0.022, noiseFloor * 2.8);
        const silenceThr = Math.max(0.012, noiseFloor * 1.5);

        if (!speech) {
          if (rms < speechThr) {
            noiseFloor = noiseFloor * 0.96 + rms * 0.04;
          }
          if (rms > speechThr) {
            speechFrames++;
            if (speechFrames >= 2) {
              speech = true;
              lastVoice = now;
              voiceEnd = total;
            }
          } else {
            speechFrames = 0;
          }
        } else {
          // When speaking, update lastVoice only if signal is above silence threshold
          if (rms > silenceThr) {
            lastVoice = now;
            voiceEnd = total;
          }
        }

        // Once speech occurred, stop as soon as silence duration exceeds silenceMs
        if (speech && now - lastVoice > silenceMs) {
          finish("silence");
        } else if (!speech && now > noSpeechMs) {
          finish("no_speech");
        } else if (now > maxMs) {
          finish("max");
        }
      };
    });
  })();
  return { stop: () => finish("manual"), done };
}

/** Browser speech recognition (used only when no server STT key is configured). */
export function browserSttSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function browserRecognize(lang, { onInterim } = {}) {
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new R();
  rec.lang = { pa: "pa-IN", hi: "hi-IN", en: "en-IN" }[lang] || "pa-IN";
  rec.interimResults = true;
  rec.continuous = true;
  rec.maxAlternatives = 1;

  let stopped = false;
  let silenceTimer = null;
  let finalTranscript = "";
  let interimTranscript = "";

  let finishResolve = null;
  const done = new Promise((resolve, reject) => {
    finishResolve = resolve;

    const finish = () => {
      if (stopped) return;
      stopped = true;
      if (silenceTimer) clearTimeout(silenceTimer);
      try { rec.stop(); } catch { /* ignore */ }
      const text = (finalTranscript + " " + interimTranscript).replace(/\s+/g, " ").trim();
      resolve({ transcript: text });
    };

    rec.onresult = (e) => {
      if (stopped) return;
      let curInterim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const item = e.results[i];
        if (item.isFinal) {
          finalTranscript += " " + item[0].transcript;
        } else {
          curInterim += " " + item[0].transcript;
        }
      }
      interimTranscript = curInterim;
      const combined = (finalTranscript + " " + interimTranscript).replace(/\s+/g, " ").trim();
      if (onInterim && combined) onInterim(combined);

      // Fast silence endpointing: 850ms pause after speech auto-completes recognition
      if (combined) {
        if (silenceTimer) clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
          finish();
        }, 850);
      }
    };

    rec.onerror = (e) => {
      if (silenceTimer) clearTimeout(silenceTimer);
      const combined = (finalTranscript + " " + interimTranscript).replace(/\s+/g, " ").trim();
      if (e.error === "no-speech") {
        resolve({ transcript: "" });
      } else if (combined) {
        resolve({ transcript: combined });
      } else {
        reject(new Error(e.error || "stt"));
      }
    };

    rec.onend = () => {
      if (!stopped) finish();
    };

    try {
      rec.start();
    } catch (err) {
      reject(err);
    }
  });

  return {
    stop: () => {
      if (!stopped && finishResolve) {
        stopped = true;
        if (silenceTimer) clearTimeout(silenceTimer);
        try { rec.stop(); } catch { /* ignore */ }
        const text = (finalTranscript + " " + interimTranscript).replace(/\s+/g, " ").trim();
        finishResolve({ transcript: text });
      }
    },
    done,
  };
}
