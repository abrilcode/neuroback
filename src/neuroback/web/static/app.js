/* NeuroBack interface.
 *
 * Live mode: state frames arrive from the Python backend over a WebSocket (ws://host/ws);
 * the closed loop and all timing run in Python.
 * Demo mode (window.NB_DEMO): a replay of recorded EEG (PhysioNet S004, Oz) with flash
 * times precomputed by the same Python engine (scripts/build_demo.py). Same interface.
 */
"use strict";

const C = {
  navy: "#0B3C7A", blue: "#3A7FC1", pale: "#8DB4D9", sky: "#0EA5E9", raw: "#A9B8C8",
  grid: "#EAF0F6", axis: "#9AA8B8", text: "#0F2742", muted: "#5B6F86", red: "#C2412D",
};
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, "Helvetica Neue", sans-serif';
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let hello = null;
let state = null;
let page = "participant";
let lastLed = 0;
let answers = [];
let transport = null;

/* ----------------------------------------------------------------- canvas helpers */
function ctx2d(cv) {
  const dpr = window.devicePixelRatio || 1;
  if (!cv.dataset.h) { cv.dataset.h = cv.getAttribute("height"); cv.style.height = cv.dataset.h + "px"; }
  const w = cv.clientWidth, h = +cv.dataset.h;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
  }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  g.font = `11px ${FONT}`;
  return [g, w, h];
}
function interp(x, xs, ys) {
  if (!xs.length) return 0;
  if (x <= xs[0]) return ys[0];
  if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
  let lo = 0, hi = xs.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] <= x) lo = m; else hi = m; }
  const f = (x - xs[lo]) / (xs[hi] - xs[lo]);
  return ys[lo] + f * (ys[hi] - ys[lo]);
}
function pct(arr, p) {
  if (!arr.length) return 1;
  const a = Array.from(arr, Math.abs).sort((x, y) => x - y);
  return a[Math.min(a.length - 1, Math.floor(p * a.length))];
}

/* EEG trace with flash markers and an aligned stimulus track */
function drawTrace(cv, s, { stim = true, alphaOnly = false } = {}) {
  const [g, W, H] = ctx2d(cv);
  const L = 46, R = 10, T = 8, B = stim ? 58 : 26;
  const pw = W - L - R, ph = H - T - B;
  const eeg = s?.eeg || [], alpha = s?.alpha || [];
  const n = eeg.length, fs = s?.fs || 250, tEnd = s?.t || 0, win = 5;
  const ts = Array.from({ length: n }, (_, i) => tEnd - (n - 1 - i) / fs);
  const lim = Math.max(10, pct(alphaOnly && alpha.length ? alpha : eeg, 0.99) * 1.25);
  const X = (t) => L + ((t - (tEnd - win)) / win) * pw;
  const Y = (v) => T + ph / 2 - (v / lim) * (ph / 2);
  // grid + axes
  g.strokeStyle = C.grid; g.lineWidth = 1;
  for (const v of [-lim / 2, 0, lim / 2]) { g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(L + pw, Y(v)); g.stroke(); }
  g.fillStyle = C.muted; g.textAlign = "right"; g.textBaseline = "middle";
  for (const v of [-lim / 2, 0, lim / 2]) g.fillText(Math.round(v), L - 8, Y(v));
  g.save(); g.translate(12, T + ph / 2); g.rotate(-Math.PI / 2); g.textAlign = "center"; g.fillText("µV", 0, 0); g.restore();
  g.textAlign = "center"; g.textBaseline = "top";
  const axisY = stim ? H - 18 : H - 18;
  for (let k = 0; k <= win; k++) {
    const x = L + (k / win) * pw;
    g.fillText(k === win ? "0 s" : `−${win - k}`, x, axisY);
  }
  if (!n) return;
  g.save(); g.beginPath(); g.rect(L, T, pw, ph); g.clip();
  if (!alphaOnly) {
    g.strokeStyle = C.raw; g.lineWidth = 1; g.beginPath();
    eeg.forEach((v, i) => { const x = X(ts[i]), y = Y(v); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
  }
  if (alpha.length === n) {
    g.strokeStyle = C.navy; g.lineWidth = 2; g.lineJoin = "round"; g.beginPath();
    alpha.forEach((v, i) => { const x = X(ts[i]), y = Y(v); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke();
  }
  const flashes = (s.flashes || []).filter((f) => f > tEnd - win && f <= tEnd);
  const ref = alpha.length === n ? alpha : eeg;
  for (const f of flashes) {
    const x = X(f), y = Y(interp(f, ts, ref));
    g.fillStyle = "rgba(14,165,233,.18)"; g.beginPath(); g.arc(x, y, 7, 0, 7); g.fill();
    g.fillStyle = C.sky; g.strokeStyle = "#fff"; g.lineWidth = 1.2; g.beginPath(); g.arc(x, y, 3.6, 0, 7); g.fill(); g.stroke();
  }
  g.restore();
  if (stim) {
    const sy = T + ph + 12, sh = 16;
    g.fillStyle = C.muted; g.textAlign = "right"; g.textBaseline = "middle"; g.fillText("LED", L - 8, sy + sh / 2);
    g.strokeStyle = C.grid; g.beginPath(); g.moveTo(L, sy + sh); g.lineTo(L + pw, sy + sh); g.stroke();
    const pwid = Math.max(2, (0.02 / win) * pw);
    g.fillStyle = C.sky;
    for (const f of flashes) g.fillRect(X(f), sy, pwid, sh);
    g.strokeStyle = "rgba(14,165,233,.28)"; g.setLineDash([2, 3]);
    for (const f of flashes) { const x = X(f); g.beginPath(); g.moveTo(x, Y(interp(f, ts, ref)) + 6); g.lineTo(x, sy - 2); g.stroke(); }
    g.setLineDash([]);
  }
}

/* Phase dial: 0° (peak) at the top, 180° (trough) at the bottom */
function drawDial(cv, target, phaseNow, hits, showTarget = true) {
  const [g, W, H] = ctx2d(cv);
  const cx = W / 2, cy = H / 2 + 4, r = Math.min(W, H) / 2 - 30;
  const P = (deg, rr) => [cx + rr * Math.sin((deg * Math.PI) / 180), cy - rr * Math.cos((deg * Math.PI) / 180)];
  g.fillStyle = "#FAFCFE"; g.strokeStyle = "#D5DEE8"; g.lineWidth = 1.5;
  g.beginPath(); g.arc(cx, cy, r, 0, 7); g.fill(); g.stroke();
  g.strokeStyle = C.grid; g.lineWidth = 1;
  g.beginPath(); g.moveTo(cx - r, cy); g.lineTo(cx + r, cy); g.moveTo(cx, cy - r); g.lineTo(cx, cy + r); g.stroke();
  if (showTarget && target != null) {
    const a0 = ((target - 20 - 90) * Math.PI) / 180, a1 = ((target + 20 - 90) * Math.PI) / 180;
    g.fillStyle = "rgba(58,127,193,.18)"; g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, r, a0, a1); g.closePath(); g.fill();
    g.strokeStyle = C.blue; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(cx, cy); g.lineTo(...P(target, r)); g.stroke(); g.setLineDash([]);
  }
  g.fillStyle = C.muted; g.textAlign = "center"; g.textBaseline = "middle"; g.font = `11px ${FONT}`;
  [[0, "0° peak"], [90, "90°"], [180, "180° trough"], [270, "270°"]].forEach(([d, l]) => {
    const [x, y] = P(d, r + (d % 180 ? 18 : 14)); g.fillText(l, x, y);
  });
  (hits || []).forEach((h, i, a) => {
    const [x, y] = P(h, r * 0.84);
    g.fillStyle = `rgba(14,165,233,${0.25 + 0.75 * ((i + 1) / a.length)})`;
    g.beginPath(); g.arc(x, y, 3.4, 0, 7); g.fill();
  });
  if (phaseNow != null) {
    g.strokeStyle = C.navy; g.lineWidth = 3; g.lineCap = "round";
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(...P(phaseNow, r * 0.66)); g.stroke();
  }
  g.fillStyle = C.navy; g.beginPath(); g.arc(cx, cy, 4.5, 0, 7); g.fill();
}

function drawSpectrum(cv, spec, iaf) {
  const [g, W, H] = ctx2d(cv);
  const L = 40, R = 10, T = 8, B = 26, pw = W - L - R, ph = H - T - B;
  if (!spec || !spec.f) {
    g.fillStyle = C.muted; g.textAlign = "center"; g.fillText("Spectrum appears after calibration", W / 2, H / 2); return;
  }
  const f = spec.f, series = [["eo", C.raw, 1.5], ["ec", C.navy, 2.2]].filter(([k]) => spec[k]);
  const all = series.flatMap(([k]) => spec[k]);
  const lo = Math.min(...all) - 0.1, hi = Math.max(...all) + 0.1;
  const X = (v) => L + ((v - 2) / 28) * pw, Y = (v) => T + ph - ((v - lo) / (hi - lo)) * ph;
  g.strokeStyle = C.grid; g.fillStyle = C.muted; g.textAlign = "center"; g.textBaseline = "top";
  for (const v of [5, 10, 15, 20, 25, 30]) {
    g.beginPath(); g.moveTo(X(v), T); g.lineTo(X(v), T + ph); g.stroke();
    if (v === 30) { g.textAlign = "right"; g.fillText("30 Hz", X(v) + 4, T + ph + 6); } else g.fillText(v, X(v), T + ph + 6);
  }
  g.save(); g.translate(12, T + ph / 2); g.rotate(-Math.PI / 2); g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("log power", 0, 0); g.restore();
  for (const [k, col, lw] of series) {
    g.strokeStyle = col; g.lineWidth = lw; g.beginPath();
    spec[k].forEach((v, i) => { const x = X(f[i]), y = Y(v); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
  }
  if (iaf) {
    g.strokeStyle = C.sky; g.setLineDash([4, 3]); g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(X(iaf), T); g.lineTo(X(iaf), T + ph); g.stroke(); g.setLineDash([]);
    g.fillStyle = C.sky; g.textAlign = "left"; g.textBaseline = "top"; g.font = `600 11px ${FONT}`;
    g.fillText(`IAF ${iaf.toFixed(2)} Hz`, X(iaf) + 6, T + 2);
  }
}

function drawResults(cv, res) {
  const [g, W, H] = ctx2d(cv);
  const L = 54, R = 16, T = 16, B = 40, pw = W - L - R, ph = H - T - B;
  if (!res) { g.fillStyle = C.muted; g.textAlign = "center"; g.fillText("No sweep yet", W / 2, H / 2); return; }
  const n = res.labels.length;
  const top = Math.max(...res.means.map((m, i) => m + res.sems[i])) * 1.15;
  const Y = (v) => T + ph - (v / top) * ph;
  g.strokeStyle = C.grid; g.fillStyle = C.muted; g.textAlign = "right"; g.textBaseline = "middle";
  for (let k = 0; k <= 4; k++) { const v = (top * k) / 4; g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(L + pw, Y(v)); g.stroke(); g.fillText(v.toFixed(2), L - 8, Y(v)); }
  g.strokeStyle = C.axis; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(L, Y(1)); g.lineTo(L + pw, Y(1)); g.stroke(); g.setLineDash([]);
  const bw = (pw / n) * 0.56;
  res.labels.forEach((lab, i) => {
    const x = L + (pw / n) * (i + 0.5), m = res.means[i], e = res.sems[i];
    g.fillStyle = res.kinds[i] === "phase" ? C.navy : C.pale;
    g.fillRect(x - bw / 2, Y(m), bw, Y(0) - Y(m));
    g.strokeStyle = C.text; g.lineWidth = 1.4; g.beginPath();
    g.moveTo(x, Y(m - e)); g.lineTo(x, Y(m + e)); g.moveTo(x - 6, Y(m + e)); g.lineTo(x + 6, Y(m + e));
    g.moveTo(x - 6, Y(m - e)); g.lineTo(x + 6, Y(m - e)); g.stroke();
    g.fillStyle = C.text; g.textAlign = "center"; g.textBaseline = "top"; g.fillText(lab, x, T + ph + 10);
  });
}

/* ----------------------------------------------------------------- UI wiring */
function toast(msg, err = false) {
  if (!msg) return;
  const el = $("#toast");
  el.textContent = msg; el.className = "toast show" + (err ? " err" : "");
  clearTimeout(toast.t); toast.t = setTimeout(() => (el.className = "toast"), 3200);
}
async function send(cmd) {
  const r = await transport.send(cmd);
  if (r && r.message) toast(r.message, !r.ok);
  return r;
}
function setPage(p) {
  page = p;
  $$(".page").forEach((el) => el.classList.toggle("active", el.id === `page-${p}`));
  $$("#steps button").forEach((b) => b.classList.toggle("active", b.dataset.page === p));
  if (state) render(state);
}

function buildStatic(h) {
  hello = h;
  $("#ver").textContent = h.version ? `v${h.version}` : "";
  $("#warning").textContent = h.warning;
  $("#age").innerHTML = h.age_bands.map((a) => `<option>${a}</option>`).join("");
  answers = h.questions.map(() => null);
  $("#screening").innerHTML = h.questions.map((q, i) => `
    <div class="q"><p>${q}</p><span class="seg" data-i="${i}">
      <button data-v="0">No</button><button data-v="1">Yes</button></span></div>`).join("");
  $$("#screening .seg button").forEach((b) => b.addEventListener("click", () => {
    const i = +b.parentElement.dataset.i; answers[i] = b.dataset.v === "1";
    b.parentElement.querySelectorAll("button").forEach((x) => (x.className = ""));
    b.className = answers[i] ? "sel-yes" : "sel-no";
  }));
  if (h.demo) {
    $("#pill-demo").hidden = false;
    $("#target").step = 45;
    $("#demo-timing").disabled = true;
  }
}

function render(s) {
  state = s;
  // header
  $("#pill-source").textContent = s.source;
  $("#pill-pid").innerHTML = s.pid ? `<span class="mono">${s.pid}</span>${s.cleared ? "" : " · not cleared"}` : "No participant";
  $("#pill-pid").className = "pill " + (s.pid ? (s.cleared ? "on" : "warn") : "");
  $("#pill-iaf").textContent = s.iaf ? `IAF ${s.iaf.toFixed(2)} Hz` : "IAF –";
  $("#pill-iaf").className = "pill " + (s.iaf ? "on" : "");
  if (s.led > lastLed) { const el = $("#led"); el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
  lastLed = s.led;
  // step gating
  const ready = s.cleared && !!s.iaf;
  const gate = { participant: true, calibrate: !!s.pid, sweep: ready, stimulate: ready, results: true };
  const done = { participant: s.cleared, calibrate: !!s.iaf, sweep: !!s.results, stimulate: false, results: !!s.results };
  $$("#steps button").forEach((b) => { b.disabled = !gate[b.dataset.page]; b.classList.toggle("done", !!done[b.dataset.page] && b.dataset.page !== page); });

  if (page === "participant") renderParticipants(s);
  if (page === "calibrate") renderCalibrate(s);
  if (page === "sweep") renderSweep(s);
  if (page === "stimulate") renderStimulate(s);
  if (page === "results") renderResults(s);
}

function renderParticipants(s) {
  const list = s.participants || [];
  $("#pcount").textContent = list.length ? `${list.length}` : "";
  const html = list.length ? list.map((p) => `
    <div class="prow ${p.pid === s.pid ? "sel" : ""}">
      <span class="pid">${p.pid}</span><span class="age">${p.age_band || ""}</span>
      <span class="badge ${p.cleared ? "ok" : "no"}">${p.cleared ? "Cleared" : "Not cleared"}</span>
      <button class="small" data-sel="${p.pid}">${p.pid === s.pid ? "Selected" : "Select"}</button>
      <button class="small ghost" data-del="${p.pid}" title="Delete participant and all data">Delete</button>
    </div>`).join("") : `<div class="empty">No participants yet.</div>`;
  const el = $("#plist");
  if (el.dataset.html !== html) {
    el.innerHTML = html; el.dataset.html = html;
    el.querySelectorAll("[data-sel]").forEach((b) => b.addEventListener("click", () => send({ cmd: "select_participant", pid: b.dataset.sel })));
    el.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
      if (confirm(`Delete ${b.dataset.del} and all associated data?`)) send({ cmd: "delete_participant", pid: b.dataset.del });
    }));
  }
}

function renderCalibrate(s) {
  drawTrace($("#cv-cal"), s, { stim: false });
  const busy = s.mode === "calibrate";
  $("#btn-eo").disabled = busy || !s.pid; $("#btn-ec").disabled = busy || !s.pid;
  $("#btn-eo").textContent = (s.cal.done.includes("eo") ? "✓ " : "") + "Eyes open · 60 s";
  $("#btn-ec").textContent = (s.cal.done.includes("ec") ? "✓ " : "") + "Eyes closed · 60 s";
  $("#cal-bar").style.width = `${Math.round((busy ? s.cal.progress : s.cal.done.length ? 1 : 0) * 100)}%`;
  $("#cal-status").textContent = busy ? `Recording ${s.cal.key === "ec" ? "eyes closed" : "eyes open"}…` :
    s.iaf ? "Calibration complete" : s.cal.done.length ? "Record eyes closed next" : "";
  $("#t-iaf").textContent = s.iaf ? `${s.iaf.toFixed(2)} Hz` : "–";
  $("#t-snr").textContent = s.iaf_snr != null ? `${s.iaf_snr.toFixed(1)} dB` : "–";
  $("#t-react").textContent = s.reactivity != null ? `× ${s.reactivity.toFixed(1)}` : "–";
  drawSpectrum($("#cv-spec"), s.spectrum, s.iaf);
}

function renderSweep(s) {
  drawTrace($("#cv-sweep"), s, { stim: true });
  const sw = s.sweep;
  const cur = sw && s.mode === "sweep" ? sw.schedule[sw.i] : null;
  const tgt = cur && cur.kind === "phase" ? parseFloat(cur.label) : null;
  drawDial($("#cv-dial-sweep"), tgt, s.phase_now, [], tgt != null);
  const running = s.mode === "sweep";
  $("#btn-sweep").disabled = running || !(s.cleared && s.iaf);
  $("#btn-sweep").textContent = running ? "Sweep running…" : s.results ? "Run again" : "Start sweep";
  $("#sweep-bar").style.width = `${Math.round((sw ? sw.progress : 0) * 100)}%`;
  $("#sweep-status").textContent = sw ? (running ? `Block ${sw.i + 1} of ${sw.n} · ${sw.label} · ${sw.stage === "on" ? "stimulating" : "stimulus-free gap"}` : `${sw.n} blocks complete`) : "";
  const html = sw ? sw.schedule.map((b, i) => {
    const cls = ["blk", b.kind === "phase" ? "phase" : "control"];
    if (i < sw.i || !running) cls.push("done");
    if (running && i === sw.i) cls.push("now");
    const lab = b.kind === "open-loop" ? "Open-loop" : b.kind === "random-phase" ? "Random" : b.label;
    return `<div class="${cls.join(" ")}" title="${b.label}">${lab}</div>`;
  }).join("") : `<div class="empty">The randomised schedule appears when the sweep starts.</div>`;
  if ($("#schedule").dataset.html !== html) { $("#schedule").innerHTML = html; $("#schedule").dataset.html = html; }
}

function renderStimulate(s) {
  drawTrace($("#cv-stim"), s, { stim: true });
  const tgt = s.mode === "stimulate" ? s.target_deg : +$("#target").value;
  drawDial($("#cv-dial"), tgt, s.phase_now, s.hits || []);
  const m = s.metrics;
  $("#m-rate").textContent = m ? m.rate.toFixed(1) : "–";
  $("#m-plv").textContent = m ? m.plv.toFixed(2) : "–";
  $("#m-err").textContent = m ? `${m.err >= 0 ? "+" : ""}${m.err.toFixed(0)}°` : "–";
  $("#m-amp").textContent = m ? `${m.amp.toFixed(1)} µV` : "–";
  const on = s.mode === "stimulate";
  $("#btn-stim").textContent = on ? "Stop stimulation" : "Start stimulation";
  $("#btn-stim").classList.toggle("running", on);
  $("#btn-stim").disabled = !(s.cleared && s.iaf) || s.mode === "sweep" || s.mode === "calibrate";
  $("#stim-status").textContent = on ? `Target ${Math.round(s.target_deg)}° · ${m ? "measuring" : "collecting flashes…"}` : "";
}

function renderResults(s) {
  drawResults($("#cv-results"), s.results);
  const r = s.results;
  $("#results-text").innerHTML = r ? `
    <div class="big"><div><span>Blocks</span><b>${r.n_blocks}</b></div>
    <div><span>Preferred phase</span><b>${Math.round(r.preferred_deg)}°</b></div>
    <div><span>Permutation p</span><b>${r.p < 0.001 ? "< 0.001" : r.p.toFixed(3)}</b></div>
    <div><span>Cosine fit R²</span><b>${r.r2.toFixed(2)}</b></div></div>
    <p>A single session is a pilot: confirm any preferred phase on new blocks before using it.${hello && hello.demo ? " Recorded EEG does not respond to the light, so no phase effect is expected in this replay." : ""}</p>`
    : "Run a phase sweep to see results.";
}

function wire() {
  $$("canvas").forEach((cv) => { cv.dataset.h = cv.getAttribute("height"); cv.style.height = cv.dataset.h + "px"; });
  $$("#steps button").forEach((b) => b.addEventListener("click", () => setPage(b.dataset.page)));
  $("#btn-stop").addEventListener("click", () => send({ cmd: "stop" }));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") send({ cmd: "stop" }); });
  $("#btn-create").addEventListener("click", () => {
    if (answers.some((a) => a === null)) return toast("Answer every screening item", true);
    send({ cmd: "create_participant", age_band: $("#age").value, answers, consent: $("#consent").checked });
  });
  $("#btn-eo").addEventListener("click", () => send({ cmd: "calibrate", eyes_closed: false }));
  $("#btn-ec").addEventListener("click", () => send({ cmd: "calibrate", eyes_closed: true }));
  $("#btn-sweep").addEventListener("click", () => send({ cmd: "start_sweep", demo_timing: $("#demo-timing").checked }));
  $("#btn-stim").addEventListener("click", () => send(state && state.mode === "stimulate" ? { cmd: "stop_stim" } : { cmd: "start_stim", target_deg: +$("#target").value }));
  const setT = (v) => { $("#target").value = v; $("#target-out").textContent = `${$("#target").value}°`; send({ cmd: "set_target", target_deg: +$("#target").value }); };
  $("#target").addEventListener("input", () => setT($("#target").value));
  $$(".presets button").forEach((b) => b.addEventListener("click", () => setT(b.dataset.t)));
  $("#btn-save").addEventListener("click", () => send({ cmd: "save" }));
  window.addEventListener("resize", () => state && render(state));
}

/* ----------------------------------------------------------------- live transport */
class Live {
  constructor() { this.pending = new Map(); this.id = 0; this.connect(); }
  connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    this.ws = ws;
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "hello") buildStatic(m);
      else if (m.type === "state") render(m);
      else if (m.type === "reply" && this.pending.has(m.id)) { this.pending.get(m.id)(m); this.pending.delete(m.id); }
    };
    ws.onclose = () => { $("#pill-source").textContent = "Disconnected · retrying…"; setTimeout(() => this.connect(), 1500); };
  }
  send(cmd) {
    return new Promise((res) => {
      const id = ++this.id; this.pending.set(id, res);
      if (this.ws.readyState === 1) this.ws.send(JSON.stringify({ ...cmd, id }));
      else res({ ok: false, message: "not connected" });
    });
  }
}

/* ----------------------------------------------------------------- demo transport */
function i16(b64, scale = 10) {
  const bin = atob(b64), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  const a = new Int16Array(u8.buffer), out = new Float32Array(a.length);
  for (let i = 0; i < a.length; i++) out[i] = a[i] / scale;
  return out;
}
const wrap180 = (d) => ((d + 540) % 360) - 180;

class Demo {
  constructor(d, params) {
    this.d = d; this.fs = d.fs; this.N = d.n; this.dur = d.n / d.fs;
    this.ec = i16(d.ec); this.eo = i16(d.eo); this.aec = i16(d.alpha_ec); this.aeo = i16(d.alpha_eo);
    this.est = i16(d.est_phase, 1);
    this.t0 = performance.now(); this.frozen = null;
    this.participants = [{ pid: "P-DEMO01", age_band: "18-29", cleared: true }];
    this.pid = "P-DEMO01"; this.cal = new Set(); this.mode = "idle"; this.target = 0;
    this.led = 0; this.lastT = 0; this.results = null; this.message = "";
    this.script(params);
    setInterval(() => render(this.frame()), 50);
  }
  now() { return this.frozen != null ? this.frozen : (performance.now() - this.t0) / 1000; }
  script(p) {
    const at = parseFloat(p.get("at") || "0");
    if (p.get("freeze")) this.frozen = at; else this.t0 -= at * 1000;
    const pg = p.get("page");
    if (pg && pg !== "participant") this.cal = new Set(["eo", "ec"]);
    if (pg === "stimulate") { this.target = +(p.get("target") || 0); this.mode = "stimulate"; this.stimT0 = at - 12; }
    if (pg === "sweep") { this.mode = "sweep"; this.sweepT0 = at - parseFloat(p.get("sweep_at") || "9"); }
    if (pg === "results") this.results = this.d.sweep.results;
    if (pg === "calibrate" && p.get("cal") !== "done") { this.mode = "calibrate"; this.calKey = "ec"; this.calT0 = at - 4.2; this.cal = new Set(["eo"]); }
  }
  flashesIn(tf, a, b, offset = 0) {
    const out = [];
    for (let k = Math.floor((a - offset) / this.dur); k <= Math.floor((b - offset) / this.dur); k++)
      tf.forEach((t, i) => { const tt = t + k * this.dur + offset; if (tt > a && tt <= b) out.push([tt, i]); });
    return out;
  }
  frame() {
    const T = this.now(), d = this.d, fs = this.fs, W = Math.round(5 * fs);
    let rec = this.ec, al = this.aec, rt = T, flashes = [], hits = [], metrics = null, phase = null, sweep = null, cal;
    const iafKnown = this.cal.has("ec");
    // calibration progress (accelerated ×10 in the demo)
    if (this.mode === "calibrate") {
      const prog = (T - this.calT0) / 6;
      if (this.calKey === "eo") { rec = this.eo; al = this.aeo; }
      if (prog >= 1) { this.cal.add(this.calKey); this.mode = "idle"; this.message = "calibration finished"; }
      cal = { key: this.calKey, progress: Math.min(1, prog), done: [...this.cal] };
    } else cal = { key: null, progress: 0, done: [...this.cal] };
    // sweep replay
    if (this.mode === "sweep") {
      const sw = d.sweep, s = T - this.sweepT0, blk = sw.on_s + sw.off_s, total = blk * sw.schedule.length;
      if (s >= total) { this.mode = "idle"; this.results = sw.results; }
      else {
        rt = sw.start_t + s;
        const i = Math.floor(s / blk), stage = s % blk < sw.on_s ? "on" : "off";
        sweep = { i, n: sw.schedule.length, stage, label: sw.schedule[i].label, schedule: sw.schedule, progress: s / total };
        flashes = sw.flashes.map((f) => f + this.sweepT0).filter((f) => f > T - 5 && f <= T);
        if (sw.schedule[i].kind === "phase" && stage === "on") phase = this.est[Math.floor((((rt % this.dur) + this.dur) % this.dur) * 25)];
        this.led += sw.flashes.filter((f) => f + this.sweepT0 > this.lastT && f + this.sweepT0 <= T).length;
      }
    }
    if (this.results && !sweep) sweep = { i: d.sweep.schedule.length, n: d.sweep.schedule.length, stage: "on", label: "", schedule: d.sweep.schedule, progress: 1 };
    // stimulation replay
    if (this.mode === "stimulate") {
      const st = d.stim[String(this.target)];
      flashes = this.flashesIn(st.t, Math.max(T - 5, this.stimT0), T).map(([t]) => t);
      this.led += this.flashesIn(st.t, Math.max(this.lastT, this.stimT0), T).length;
      phase = this.est[Math.floor((T % this.dur) * 25)];
      const recent = this.flashesIn(st.t, Math.max(T - 8 + 1, this.stimT0), T - 1);
      if (recent.length >= 5) {
        const ph = recent.map(([, i]) => st.ph[i]);
        const err = ph.map((p) => ((wrap180(p - this.target)) * Math.PI) / 180);
        const cs = err.reduce((a, e) => a + Math.cos(e), 0) / err.length, sn = err.reduce((a, e) => a + Math.sin(e), 0) / err.length;
        metrics = { plv: Math.hypot(cs, sn), err: (Math.atan2(sn, cs) * 180) / Math.PI,
          rate: (recent.length - 1) / (recent[recent.length - 1][0] - recent[0][0] + 1e-9), amp: d.amp_median };
        hits = ph.slice(-80);
      }
    }
    this.lastT = T;
    // display window
    const end = Math.floor(rt * fs);
    const eeg = new Array(W), alpha = new Array(W);
    for (let k = 0; k < W; k++) { const j = (((end - W + 1 + k) % this.N) + this.N) % this.N; eeg[k] = rec[j]; alpha[k] = al[j]; }
    return {
      source: d.source, fs, t: T, pid: this.pid, cleared: !!this.participants.find((p) => p.pid === this.pid && p.cleared),
      participants: this.participants, iaf: iafKnown ? d.iaf : null, iaf_snr: iafKnown ? d.iaf_snr : null,
      reactivity: iafKnown && this.cal.has("eo") ? d.reactivity : null, mode: this.mode, target_deg: this.target,
      eeg, alpha: iafKnown ? alpha : [], flashes, phase_now: phase, hits, metrics, cal,
      spectrum: this.cal.size ? { f: d.spectrum.f, ...(this.cal.has("ec") ? { ec: d.spectrum.ec } : {}), ...(this.cal.has("eo") ? { eo: d.spectrum.eo } : {}) } : null,
      sweep, results: this.results, led: this.led, message: this.message,
    };
  }
  async send(c) {
    const T = this.now(), ready = this.cal.has("ec") && this.participants.find((p) => p.pid === this.pid && p.cleared);
    switch (c.cmd) {
      case "create_participant": {
        const pid = "P-" + Math.random().toString(16).slice(2, 8).toUpperCase();
        const cleared = c.consent && c.answers.every((a) => !a);
        this.participants.push({ pid, age_band: c.age_band, cleared }); this.pid = pid;
        return { ok: true, message: `${pid} created${cleared ? "" : ", not cleared for flashing-light stimulation"} (demo: kept in this browser tab only)` };
      }
      case "select_participant": this.pid = c.pid; return { ok: true };
      case "delete_participant": this.participants = this.participants.filter((p) => p.pid !== c.pid); if (this.pid === c.pid) this.pid = null; return { ok: true };
      case "calibrate":
        if (!this.pid) return { ok: false, message: "select a participant first" };
        this.mode = "calibrate"; this.calKey = c.eyes_closed ? "ec" : "eo"; this.calT0 = T;
        return { ok: true, message: "Demo replays the recording; calibration runs 10× faster than real time" };
      case "start_sweep":
        if (!ready) return { ok: false, message: "calibrate first (eyes closed)" };
        this.mode = "sweep"; this.sweepT0 = T; this.results = null; return { ok: true };
      case "start_stim":
        if (!ready) return { ok: false, message: "calibrate first (eyes closed)" };
        this.target = Math.round((c.target_deg % 360) / 45) * 45 % 360; this.mode = "stimulate"; this.stimT0 = T; return { ok: true };
      case "stop_stim": if (this.mode === "stimulate") this.mode = "idle"; return { ok: true };
      case "set_target": this.target = Math.round((c.target_deg % 360) / 45) * 45 % 360; return { ok: true };
      case "stop": this.mode = "idle"; return { ok: true, message: "stopped" };
      case "save": return { ok: false, message: "Saving is available in the desktop app; the online demo stores nothing" };
    }
    return { ok: false, message: "unknown command" };
  }
}

/* ----------------------------------------------------------------- boot */
async function boot() {
  wire();
  const params = new URLSearchParams(location.search);
  if (window.NB_DEMO) {
    const d = await (await fetch("data.json")).json();
    buildStatic({ ...d.hello, demo: true, version: d.version });
    transport = new Demo(d, params);
  } else {
    transport = new Live();
  }
  setPage(params.get("page") || "participant");
}
boot();
