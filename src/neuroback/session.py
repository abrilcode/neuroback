"""Session state machine, independent of any user interface.

Participant -> calibration (eyes open / eyes closed) -> phase sweep -> stimulation.
``Session.tick()`` pulls new samples from the source and drives the closed loop;
``Session.command()`` applies UI actions; ``Session.snapshot()`` returns everything the
interface needs to draw. The web app (``neuroback.web``) and the tests both use it.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque

import numpy as np

from .analysis import circ_mean_deg, phase_at, phase_dependence_test, plv, wrap
from .closedloop import ClosedLoop, OpenLoop, RandomPhase
from .dsp import band_power, individual_alpha_frequency, offline_phase, welch_psd
from .phase import ARForecast, EcHT
from .protocol import SweepConfig
from .safety import SCREENING_QUESTIONS, WARNING, Screening
from .stimulators import Stimulator, TriggerScheduler, VirtualStimulator
from .storage import Store

DISPLAY_S = 5.0
TICK_S = 0.02
AGE_BANDS = ("18-29", "30-44", "45-64", "65+")


class Session:
    def __init__(self, source, stimulator: Stimulator | None = None, data_dir="neuroback-data",
                 latency_ms: float = 0.0, estimator: str = "ecHT", realtime: bool | None = None):
        self.source = source
        self.fs = float(source.fs)
        self.realtime = getattr(source, "realtime", True) if realtime is None else realtime
        self.store = Store(data_dir)
        self.lock = threading.RLock()
        self.latency_s = latency_ms / 1000
        self.estimator_name = estimator

        self.pid: str | None = None
        self.iaf: float | None = None
        self.iaf_snr: float | None = None
        self.reactivity: float | None = None
        self.amp_gate: float | None = None
        self.spectrum: dict | None = None
        self.cal: dict[str, np.ndarray] = {}
        self.cal_key: str | None = None
        self.cal_buf: list[np.ndarray] = []
        self.cal_needed = int(60 * self.fs)

        self.display: deque[float] = deque(maxlen=int(DISPLAY_S * self.fs))
        self.history: deque[float] = deque(maxlen=int(30 * self.fs))
        self.n_total = 0
        self.flash_times: deque[float] = deque(maxlen=600)  # sample-clock seconds
        self.flash_count = 0
        self.engine = None
        self.mode = "idle"  # idle | calibrate | sweep | stimulate
        self.target_deg = 0.0
        self.stim_t0 = 0.0
        self.recording: list[np.ndarray] = []
        self.events: list[dict] = []
        self.sweep_cfg: SweepConfig | None = None
        self.sweep_blocks: list = []
        self.sweep_rows: list[dict] = []
        self.results: dict | None = None
        self.message = ""

        self.stim = stimulator or VirtualStimulator()
        self.sched = TriggerScheduler(self.stim) if self.realtime else None
        self.source.start()

    # ------------------------------------------------------------------ participants
    def create_participant(self, age_band: str | None, answers, consent: bool) -> str:
        answers = tuple(bool(a) for a in answers)
        if len(answers) != len(SCREENING_QUESTIONS):
            raise ValueError("answer every screening item")
        scr = Screening(answers, bool(consent))
        pid = self.store.add_participant(age_band, scr.passed, bool(consent))
        self.select_participant(pid)
        self.message = f"{pid} created" + ("" if scr.passed else ", not cleared for flashing-light stimulation")
        return pid

    def select_participant(self, pid: str) -> None:
        if pid not in {p[0] for p in self.store.participants()}:
            raise ValueError(f"unknown participant {pid}")
        self.pid = pid

    def delete_participant(self, pid: str) -> None:
        self.store.delete_participant(pid)
        if self.pid == pid:
            self.pid = None

    @property
    def cleared(self) -> bool:
        return bool(self.pid and self.store.can_stimulate(self.pid))

    def _require_ready(self) -> None:
        if not self.cleared:
            raise PermissionError("select a participant who passed screening and gave consent")
        if self.iaf is None:
            raise PermissionError("record eyes closed first to find the individual alpha frequency")

    # ------------------------------------------------------------------ calibration
    def start_calibration(self, eyes_closed: bool, seconds: float = 60.0) -> None:
        if not self.pid:
            raise PermissionError("select a participant first")
        if hasattr(self.source, "eyes_closed"):
            self.source.eyes_closed = eyes_closed
        self._halt_engine()
        self.cal_key = "ec" if eyes_closed else "eo"
        self.cal_buf = []
        self.cal_needed = int(seconds * self.fs)
        self.mode = "calibrate"

    def _finish_calibration(self) -> None:
        x = np.concatenate(self.cal_buf)[: self.cal_needed]
        self.cal[self.cal_key] = x
        self.events.append({"t": round(self.n_total / self.fs, 3), "event": f"calibration_{self.cal_key}"})
        self.mode = "idle"
        if "ec" in self.cal:
            ec = self.cal["ec"]
            peak = individual_alpha_frequency(ec, self.fs)
            self.iaf, self.iaf_snr = float(peak.freq), float(peak.snr_db)
            _, amp, _ = offline_phase(ec, self.fs, self.iaf)
            self.amp_gate = float(np.quantile(amp, 0.25))
            band = (self.iaf - 2, self.iaf + 2)
            if "eo" in self.cal:
                self.reactivity = band_power(ec, self.fs, band) / max(1e-12, band_power(self.cal["eo"], self.fs, band))
        f = None
        spec = {}
        for key, x in self.cal.items():
            f, p = welch_psd(x, self.fs, resolution_hz=0.25)
            m = (f >= 2) & (f <= 30)
            spec[key] = np.log10(p[m]).round(3).tolist()
            spec["f"] = f[m].round(2).tolist()
        self.spectrum = spec
        self.message = f"calibration ({'eyes closed' if self.cal_key == 'ec' else 'eyes open'}) finished"

    # ------------------------------------------------------------------ closed loop
    def _make_engine(self, target_deg: float):
        est = EcHT(self.fs, self.iaf) if self.estimator_name == "ecHT" else ARForecast(self.fs, self.iaf)
        loop = ClosedLoop(self.fs, est, f0=self.iaf, target_deg=target_deg, latency_s=self.latency_s,
                          commit_s=TICK_S * 1.25, amp_threshold=self.amp_gate)
        h = np.fromiter(self.history, float)
        if len(h) >= len(loop.buf):
            loop.buf[:] = h[-len(loop.buf):]
        loop.n_seen = self.n_total
        return loop

    def _sync(self, eng):
        eng.n_seen = self.n_total
        return eng

    def _halt_engine(self) -> None:
        self.engine = None
        if self.sched:
            self.sched.cancel()

    def start_stimulation(self, target_deg: float) -> None:
        self._require_ready()
        self.target_deg = float(target_deg) % 360
        self.engine = self._make_engine(self.target_deg)
        self.mode = "stimulate"
        self.stim_t0 = self.n_total / self.fs
        self.events.append({"t": round(self.stim_t0, 3), "event": "stim_start", "target_deg": self.target_deg})

    def stop_stimulation(self) -> None:
        if self.mode == "stimulate":
            self._halt_engine()
            self.mode = "idle"
            self.events.append({"t": round(self.n_total / self.fs, 3), "event": "stim_stop"})

    def set_target(self, target_deg: float) -> None:
        self.target_deg = float(target_deg) % 360
        if self.mode == "stimulate" and isinstance(self.engine, ClosedLoop):
            self.engine.set_target(self.target_deg)
            if self.sched:
                self.sched.cancel()

    def emergency_stop(self) -> None:
        self._halt_engine()
        self.mode = "idle"
        self.events.append({"t": round(self.n_total / self.fs, 3), "event": "EMERGENCY_STOP"})
        self.message = "stopped"

    # ------------------------------------------------------------------ sweep
    def start_sweep(self, demo_timing: bool = False, seed: int | None = None) -> None:
        self._require_ready()
        self.sweep_cfg = SweepConfig(repeats=2, on_s=4, off_s=2, seed=seed) if demo_timing else SweepConfig(seed=seed)
        self.sweep_blocks = self.sweep_cfg.schedule()
        self.sweep_rows = []
        self.results = None
        self.flash_times.clear()
        self.block_i = -1
        self.mode = "sweep"
        self._next_block()

    def _next_block(self) -> None:
        self.block_i += 1
        if self.block_i >= len(self.sweep_blocks):
            self._halt_engine()
            self.mode = "idle"
            self.results = self.summarise_sweep()
            self.message = "sweep finished"
            return
        cond = self.sweep_blocks[self.block_i]
        self.block_cond = cond
        self.block_stage = "on"
        self.block_start = self.n_total
        self.block_samples: list[np.ndarray] = []
        if cond.kind == "phase":
            self.engine = self._make_engine(cond.target_deg)
        elif cond.kind == "open-loop":
            self.engine = self._sync(OpenLoop(self.fs, self.iaf))
        else:
            self.engine = self._sync(RandomPhase(self.fs, self.iaf))
        self.events.append({"t": round(self.n_total / self.fs, 3), "event": "block_on", "condition": cond.label})

    def _sweep_step(self, chunk: np.ndarray) -> None:
        cfg = self.sweep_cfg
        self.block_samples.append(chunk)
        elapsed = (self.n_total - self.block_start) / self.fs
        band = (self.iaf - 2, self.iaf + 2)
        if self.block_stage == "on" and elapsed >= cfg.on_s:
            on = np.concatenate(self.block_samples)
            self.block_on_power = band_power(on[int(self.fs):], self.fs, band)
            self.block_stage = "off"
            self._halt_engine()
            self.block_samples = []
            self.block_start = self.n_total
            self.events.append({"t": round(self.n_total / self.fs, 3), "event": "block_off"})
        elif self.block_stage == "off" and elapsed >= cfg.off_s:
            off = np.concatenate(self.block_samples)
            c = self.block_cond
            self.sweep_rows.append({"condition": c.label, "kind": c.kind, "target_deg": c.target_deg,
                                    "alpha_on": self.block_on_power,
                                    "alpha_off": band_power(off[int(0.5 * self.fs):], self.fs, band)})
            self._next_block()

    def summarise_sweep(self) -> dict | None:
        rows = self.sweep_rows
        if not rows or self.sweep_cfg is None:
            return None
        base = float(np.mean([r["alpha_off"] for r in rows])) or 1.0
        labels, kinds, means, sems = [], [], [], []
        for cond in self.sweep_cfg.conditions():
            vals = np.array([r["alpha_off"] / base for r in rows if r["condition"] == cond.label])
            labels.append(cond.label)
            kinds.append(cond.kind)
            means.append(float(vals.mean()))
            sems.append(float(vals.std(ddof=1) / math.sqrt(len(vals))) if len(vals) > 1 else 0.0)
        ph = [r for r in rows if r["kind"] == "phase"]
        test = phase_dependence_test(np.radians([r["target_deg"] for r in ph]), [r["alpha_off"] for r in ph], n_perm=2000)
        return {"labels": labels, "kinds": kinds, "means": means, "sems": sems, "n_blocks": len(rows),
                "preferred_deg": round(test["preferred_deg"], 1), "p": round(test["p"], 4), "r2": round(test["r2"], 3)}

    # ------------------------------------------------------------------ loop
    def tick(self, n: int | None = None) -> None:
        with self.lock:
            chunk = self.source.read(n) if n is not None else self.source.read()
            receipt = time.perf_counter()
            if len(chunk) == 0:
                return
            self.display.extend(chunk)
            self.history.extend(chunk)
            self.n_total += len(chunk)
            t_newest = (self.n_total - 1) / self.fs
            if self.mode in ("sweep", "stimulate"):
                self.recording.append(chunk)
            if self.engine is not None:
                for t in self.engine.push(chunk):
                    self._on_fired(t, receipt, t_newest)
                pending = getattr(self.engine, "pending", None)
                if self.sched and pending is not None:
                    # anchor to the arrival time of the newest sample: immune to drift
                    # between the amplifier's sample clock and the host clock
                    self.sched.tentative(receipt + (pending - t_newest))
            if self.mode == "calibrate":
                self.cal_buf.append(chunk)
                if sum(len(c) for c in self.cal_buf) >= self.cal_needed:
                    self._finish_calibration()
            elif self.mode == "sweep":
                self._sweep_step(chunk)

    def _on_fired(self, t: float, receipt: float, t_newest: float) -> None:
        self.flash_times.append(t)
        self.flash_count += 1
        self.events.append({"t": round(t, 4), "event": "flash"})
        if self.sched:
            self.sched.commit(receipt + (t - t_newest))

    # ------------------------------------------------------------------ commands + snapshot
    def command(self, msg: dict) -> dict:
        cmd = msg.get("cmd")
        try:
            with self.lock:
                if cmd == "create_participant":
                    pid = self.create_participant(msg.get("age_band"), msg.get("answers", []), msg.get("consent", False))
                    return {"ok": True, "pid": pid, "message": self.message}
                if cmd == "select_participant":
                    self.select_participant(msg["pid"])
                elif cmd == "delete_participant":
                    self.delete_participant(msg["pid"])
                elif cmd == "calibrate":
                    self.start_calibration(bool(msg.get("eyes_closed")), float(msg.get("seconds", 60)))
                elif cmd == "start_sweep":
                    self.start_sweep(bool(msg.get("demo_timing")))
                elif cmd == "start_stim":
                    self.start_stimulation(float(msg.get("target_deg", 0)))
                elif cmd == "stop_stim":
                    self.stop_stimulation()
                elif cmd == "set_target":
                    self.set_target(float(msg.get("target_deg", 0)))
                elif cmd == "stop":
                    self.emergency_stop()
                elif cmd == "save":
                    sid = self.save()
                    return {"ok": True, "message": f"session {sid} saved for {self.pid}"}
                else:
                    return {"ok": False, "message": f"unknown command {cmd!r}"}
            return {"ok": True, "message": self.message}
        except (PermissionError, ValueError, KeyError) as err:
            return {"ok": False, "message": str(err).strip("'")}

    def save(self) -> int:
        if not self.pid or not self.recording:
            raise ValueError("run a sweep or stimulation first")
        return self.store.save_session(self.pid, np.concatenate(self.recording), self.fs, self.events, self.iaf,
                                       {"estimator": self.estimator_name, "latency_s": self.latency_s,
                                        "sweep": self.sweep_rows})

    def _accuracy(self):
        if self.mode != "stimulate" or not self.iaf or len(self.history) < 6 * self.fs:
            return None, []
        h = np.fromiter(self.history, float)[-int(8 * self.fs):]
        t_end = self.n_total / self.fs
        t0 = t_end - len(h) / self.fs
        truth, amp, _ = offline_phase(h, self.fs, self.iaf)
        f = np.array([x for x in self.flash_times if max(t0 + 1, self.stim_t0) < x < t_end - 1])
        if len(f) < 5:
            return None, []
        ph = phase_at(f - t0, truth, self.fs)
        err = wrap(ph - math.radians(self.target_deg))
        metrics = {"plv": round(plv(err), 3), "err": round(circ_mean_deg(err), 1),
                   "rate": round((len(f) - 1) / (f[-1] - f[0] + 1e-9), 2), "amp": round(float(np.median(amp)), 1)}
        return metrics, (np.degrees(ph) % 360).round(1).tolist()

    def snapshot(self) -> dict:
        with self.lock:
            y = np.fromiter(self.display, float)
            t_end = self.n_total / self.fs
            alpha = []
            if self.iaf and len(y) > 60:
                alpha = offline_phase(y, self.fs, self.iaf)[2].round(2).tolist()
            phase_now = None
            if isinstance(self.engine, ClosedLoop) and len(self.history) >= self.engine.est.window:
                e = self.engine.est.estimate(np.fromiter(self.history, float)[-self.engine.est.window:])
                phase_now = round(math.degrees(e.phase) % 360, 1)
            metrics, hits = self._accuracy()
            sweep = None
            if self.sweep_blocks and (self.mode == "sweep" or self.results):
                i = min(getattr(self, "block_i", 0), len(self.sweep_blocks))
                cfg = self.sweep_cfg
                stage = getattr(self, "block_stage", "on")
                elapsed = (self.n_total - getattr(self, "block_start", self.n_total)) / self.fs
                frac = (elapsed + (cfg.on_s if stage == "off" else 0)) / (cfg.on_s + cfg.off_s)
                sweep = {"i": i, "n": len(self.sweep_blocks), "stage": stage,
                         "label": self.sweep_blocks[i].label if i < len(self.sweep_blocks) else "",
                         "schedule": [{"label": c.label, "kind": c.kind} for c in self.sweep_blocks],
                         "progress": min(1.0, (i + min(1.0, frac)) / len(self.sweep_blocks)) if self.mode == "sweep" else 1.0}
            cal = {"key": self.cal_key if self.mode == "calibrate" else None,
                   "progress": (sum(len(c) for c in self.cal_buf) / self.cal_needed) if self.mode == "calibrate" else 0,
                   "done": sorted(self.cal)}
            return {
                "source": self.source.label, "fs": self.fs, "t": round(t_end, 3),
                "pid": self.pid, "cleared": self.cleared,
                "participants": [{"pid": p, "age_band": a, "cleared": bool(c)} for p, a, c in self.store.participants()],
                "iaf": self.iaf, "iaf_snr": self.iaf_snr, "reactivity": self.reactivity,
                "mode": self.mode, "target_deg": self.target_deg, "message": self.message,
                "eeg": y.round(2).tolist(), "alpha": alpha,
                "flashes": [round(f, 4) for f in self.flash_times if f > t_end - DISPLAY_S],
                "phase_now": phase_now, "hits": hits[-80:], "metrics": metrics,
                "cal": cal, "spectrum": self.spectrum, "sweep": sweep, "results": self.results,
                "led": self.flash_count,
            }

    @staticmethod
    def hello() -> dict:
        return {"questions": list(SCREENING_QUESTIONS), "warning": WARNING, "age_bands": list(AGE_BANDS)}

    def close(self) -> None:
        if self.sched:
            self.sched.stop()
        self.source.stop()
        self.stim.close()
