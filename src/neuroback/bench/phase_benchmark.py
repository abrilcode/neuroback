"""Benchmark: how accurately does each trigger rule hit a target alpha phase on real EEG?

For every subject's 1-minute eyes-closed recording (PhysioNet EEGMMIDB, channel Oz,
resampled 160 -> 250 Hz to match the Cyton):

1. estimate the individual alpha frequency (IAF) from the recording;
2. compute the non-causal "ground-truth" phase (zero-phase band-pass IAF +- 2 Hz + Hilbert);
3. stream the recording in 4-sample (16 ms) chunks through each rule, aiming at the alpha
   peak (0 deg). Sample-by-sample delivery (Cyton with the 1 ms FTDI fix) is easier; the
   Cyton's default buffering delivers ~60-sample bursts (Knierim et al. 2023), which would
   make the 2023 rule's dropped-sample bug far worse. 4 samples is a middle ground;
4. read the ground-truth phase at every stimulus time.

The 2023 rule gets an oracle delay: the single delay that best aligns its triggers with
the target for that subject, i.e. what a perfect delay sweep would have found. Settings
of the new estimators were chosen on synthetic data only (scripts/_tune_synthetic.py).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from ..analysis import circ_mean_deg, circ_sd_deg, phase_at, plv, wrap
from ..closedloop import ClosedLoop, run_offline
from ..dsp import individual_alpha_frequency, offline_phase, resample
from ..phase import ARForecast, EcHT, LegacyZeroCrossing
from .physionet import DEFAULT_DIR, fetch, occipital_channel

FS = 250.0
CHUNK = 4
METHODS = ("2023 rule, as shipped", "2023 rule, fixed input", "AR forecast", "ecHT")


def _oracle_delay(times, truth, f0, target):
    """Shift trigger times by the delay that centres them on ``target`` (best case)."""
    if len(times) == 0:
        return times
    mean = math.radians(circ_mean_deg(phase_at(times, truth, FS)))
    return times + ((target - mean) % (2 * math.pi)) / (2 * math.pi * f0)


def triggers(method: str, x, f0, truth, target_deg=0.0):
    target = math.radians(target_deg)
    if method.startswith("2023"):
        rule = LegacyZeroCrossing(FS, f0, drop_extra_samples="shipped" in method)
        return _oracle_delay(run_offline(x, FS, rule, chunk=CHUNK), truth, f0, target)
    est = EcHT(FS, f0) if method == "ecHT" else ARForecast(FS, f0)
    return run_offline(x, FS, ClosedLoop(FS, est, f0=f0, target_deg=target_deg), chunk=CHUNK)


def summarise(err, amp_at, amp_q, n_cycles):
    q = np.digitize(amp_at, amp_q)  # 0..3 amplitude quartile of the alpha envelope
    return {
        "n": int(len(err)),
        "plv": plv(err),
        "mean_err_deg": circ_mean_deg(err),
        "circ_sd_deg": circ_sd_deg(err),
        "cycle_coverage": float(len(err) / n_cycles),
        "plv_by_quartile": [plv(err[q == k]) if np.any(q == k) else None for k in range(4)],
    }


def run(data_dir: Path = DEFAULT_DIR, subjects=range(1, 110), out: Path = Path("results"), jitter_ms=3.0, seed=0):
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    paths = fetch(subjects, out_dir=data_dir, verbose=False)
    rows, pooled = [], {m: [] for m in METHODS}
    pooled_jit = {m: [] for m in METHODS}
    targets = {t: [] for t in (0, 90, 180, 270)}
    t0 = time.time()
    for p in paths:
        x160, fs_in, ch = occipital_channel(p)
        x = resample(x160, fs_in, FS)
        peak = individual_alpha_frequency(x, FS)
        f0 = float(np.clip(peak.freq, 7.5, 13.0))
        truth, amp, _ = offline_phase(x, FS, f0)
        amp_q = np.quantile(amp, [0.25, 0.5, 0.75])
        n_cycles = len(x) / FS * f0
        row = {"subject": p.stem[:4], "iaf_hz": round(f0, 2), "alpha_snr_db": round(peak.snr_db, 2), "peak_found": peak.found}
        for m in METHODS:
            t = triggers(m, x, f0, truth)
            err = phase_at(t, truth, FS)
            row[m] = summarise(err, np.interp(t * FS, np.arange(len(amp)), amp), amp_q, n_cycles)
            tj = t + rng.normal(0, jitter_ms / 1000, size=len(t))
            ej = phase_at(tj, truth, FS)
            row[m]["plv_jitter"] = plv(ej)
            pooled[m].append(np.round(np.degrees(err)).astype(np.int16))
            pooled_jit[m].append(np.round(np.degrees(ej)).astype(np.int16))
        for tgt in targets:
            t = triggers("ecHT", x, f0, truth, target_deg=tgt)
            targets[tgt].append(circ_mean_deg(wrap(phase_at(t, truth, FS) - math.radians(tgt))))
        rows.append(row)
        print(f"{row['subject']}  IAF {f0:5.2f} Hz  SNR {peak.snr_db:5.1f} dB  " + "  ".join(
            f"{m.split(',')[0][:9]}:{row[m]['plv']:.2f}" for m in METHODS), flush=True)
    np.savez_compressed(
        out / "pooled_errors.npz",
        **{m: np.concatenate(v) for m, v in pooled.items()},
        **{f"{m} | jitter": np.concatenate(v) for m, v in pooled_jit.items()},
    )
    summary = {
        "dataset": "PhysioNet EEGMMIDB run 2 (eyes closed), channel Oz, 160->250 Hz",
        "n_subjects": len(rows),
        "chunk_samples": CHUNK,
        "jitter_ms": jitter_ms,
        "target_deg": 0,
        "ecHT_mean_error_by_target_deg": {str(k): float(np.median(v)) for k, v in targets.items()},
        "seconds": round(time.time() - t0, 1),
        "subjects": rows,
    }
    (out / "benchmark.json").write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    run()
