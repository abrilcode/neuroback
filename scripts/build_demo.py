"""Build the online demo (docs/demo/) and the README screenshots of the interface.

    python scripts/build_demo.py                 # data + static files
    python scripts/build_demo.py --screenshots   # also docs/figures/app-*.png (needs Google Chrome)

The demo replays real EEG (PhysioNet EEGMMIDB subject 4, channel Oz: run 1 eyes open, run 2
eyes closed). Every flash time it shows was computed here by NeuroBack's own closed loop
(ecHT, 8 target phases) and every sweep block by ``neuroback.session.Session``.
"""

from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import math
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neuroback import __version__  # noqa: E402
from neuroback.analysis import phase_at  # noqa: E402
from neuroback.bench.physionet import fetch, occipital_channel  # noqa: E402
from neuroback.closedloop import ClosedLoop, run_offline  # noqa: E402
from neuroback.dsp import band_power, individual_alpha_frequency, offline_phase, resample, welch_psd  # noqa: E402
from neuroback.phase import EcHT  # noqa: E402
from neuroback.session import Session  # noqa: E402
from neuroback.sources import ArrayPlayback  # noqa: E402

STATIC = ROOT / "src" / "neuroback" / "web" / "static"
OUT = ROOT / "docs" / "demo"
FIG = ROOT / "docs" / "figures"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FS = 250.0
SUBJECT = 4


def b64_i16(x, scale=10.0) -> str:
    return base64.b64encode(np.clip(np.round(np.asarray(x) * scale), -32768, 32767).astype("<i2").tobytes()).decode()


def load(run: int) -> np.ndarray:
    x160, fs_in, _ = occipital_channel(fetch([SUBJECT], run=run, verbose=False)[0])
    return resample(x160, fs_in, FS)[: int(60 * FS)]


def build() -> dict:
    ec, eo = load(2), load(1)
    n = len(ec)
    peak = individual_alpha_frequency(ec, FS)
    iaf = float(peak.freq)
    tiled = np.tile(ec, 3)  # loop the recording so filters have no edges
    truth = offline_phase(tiled, FS, iaf)[0]
    alpha_ec = offline_phase(tiled, FS, iaf)[2][n:2 * n]
    alpha_eo = offline_phase(np.tile(eo, 3), FS, iaf)[2][n:2 * n]
    amp = offline_phase(ec, FS, iaf)[1]
    amp_gate = float(np.quantile(amp, 0.25))

    # causal ecHT phase estimate every 10 samples (25 Hz) for the dial needle
    est = EcHT(FS, iaf)
    w = est.window
    lead = np.concatenate([ec[-w:], ec])
    est_phase = [math.degrees(est.estimate(lead[k:k + w]).phase) % 360 for k in range(0, n, 10)]

    # closed-loop flash times for 8 target phases, measured against the non-causal phase
    stim = {}
    for tgt in range(0, 360, 45):
        loop = ClosedLoop(FS, EcHT(FS, iaf), f0=iaf, target_deg=tgt, amp_threshold=amp_gate)
        t = run_offline(tiled[: 2 * n], FS, loop, chunk=5)
        t = t[(t >= n / FS) & (t < 2 * n / FS)]
        ph = np.degrees(phase_at(t, truth, FS)) % 360
        stim[str(tgt)] = {"t": np.round(t - n / FS, 4).tolist(), "ph": np.round(ph, 1).tolist()}

    band = (iaf - 2, iaf + 2)
    spec = {}
    for key, x in (("ec", ec), ("eo", eo)):
        f, p = welch_psd(x, FS, resolution_hz=0.25)
        m = (f >= 2) & (f <= 30)
        spec[key] = np.log10(p[m]).round(3).tolist()
        spec["f"] = f[m].round(2).tolist()

    # a demo-timing phase sweep, run by the real Session on the looped recording
    with tempfile.TemporaryDirectory() as td:
        s = Session(ArrayPlayback(ec, FS, label="replay", realtime=False), data_dir=td, realtime=False)
        s.create_participant("18-29", [False] * 5, True)
        s.iaf, s.amp_gate = iaf, amp_gate
        for _ in range(int(2 * FS / 5)):
            s.tick(5)
        start = s.n_total / FS
        s.start_sweep(demo_timing=True, seed=7)
        while s.mode == "sweep":
            s.tick(5)
        sweep = {"schedule": [{"label": c.label, "kind": c.kind} for c in s.sweep_blocks],
                 "on_s": s.sweep_cfg.on_s, "off_s": s.sweep_cfg.off_s, "start_t": round(start % (n / FS), 3),
                 "flashes": [round(f - start, 4) for f in s.flash_times], "results": s.results}
        s.close()

    return {
        "version": __version__, "fs": FS, "n": n, "source": f"Replay · PhysioNet S{SUBJECT:03d} · Oz · 250 Hz",
        "hello": Session.hello(),
        "ec": b64_i16(ec), "eo": b64_i16(eo), "alpha_ec": b64_i16(alpha_ec), "alpha_eo": b64_i16(alpha_eo),
        "est_phase": b64_i16(est_phase, 1.0),
        "iaf": round(iaf, 2), "iaf_snr": round(float(peak.snr_db), 1),
        "reactivity": round(band_power(ec, FS, band) / band_power(eo, FS, band), 2),
        "amp_median": round(float(np.median(amp)), 1), "spectrum": spec, "stim": stim, "sweep": sweep,
    }


def write(data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in ("style.css", "app.js", "favicon.svg"):
        shutil.copy(STATIC / f, OUT / f)
    html = (STATIC / "index.html").read_text()
    html = html.replace('<script src="app.js"></script>', '<script>window.NB_DEMO = true;</script>\n<script src="app.js"></script>')
    (OUT / "index.html").write_text(html)
    (OUT / "data.json").write_text(json.dumps(data, separators=(",", ":")))
    (ROOT / "docs" / ".nojekyll").write_text("")
    (ROOT / "docs" / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>NeuroBack</title>'
        '<meta http-equiv="refresh" content="0; url=demo/"><a href="demo/">NeuroBack online demo</a>\n')


SHOTS = {
    "app-participant": "page=participant",
    "app-calibrate": "page=calibrate&at=24&freeze=1&cal=done",
    "app-sweep": "page=sweep&at=40&sweep_at=9.6&freeze=1",
    "app-stimulate": "page=stimulate&at=31&freeze=1&target=0",
    "app-results": "page=results&at=10&freeze=1",
}


def screenshots() -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "docs"))
    handler.log_message = lambda *a: None
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        for name, q in SHOTS.items():
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1440,900",
                            "--force-device-scale-factor=1.5", "--virtual-time-budget=4000",
                            f"--screenshot={FIG / (name + '.png')}", f"http://127.0.0.1:{port}/demo/?{q}"],
                           check=True, capture_output=True)
            print("wrote", FIG / (name + ".png"))
        httpd.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", action="store_true")
    a = ap.parse_args()
    data = build()
    write(data)
    print("demo written to", OUT, f"({(OUT / 'data.json').stat().st_size // 1024} KB data)")
    if a.screenshots:
        screenshots()
