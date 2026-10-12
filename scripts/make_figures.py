"""Generate every figure in the README and docs from code and data.

    python scripts/make_figures.py                  # needs results/ from `neuroback benchmark`
    python scripts/make_figures.py --legacy-csv path/to/EV-EEG*.csv   # also the 2023 audit figure

Nothing here is drawn by hand: the benchmark plots read results/benchmark.json, the hero
and demo animation run the real closed loop on PhysioNet EEG, and the evidence map plots
published effect sizes listed (with sources) in EVIDENCE below.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import Wedge
from scipy import signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neuroback.analysis import phase_at, plv  # noqa: E402
from neuroback.bench.physionet import fetch, occipital_channel  # noqa: E402
from neuroback.closedloop import ClosedLoop, run_offline  # noqa: E402
from neuroback.dsp import individual_alpha_frequency, offline_phase, resample  # noqa: E402
from neuroback.phase import EcHT  # noqa: E402

FIG = ROOT / "docs" / "figures"
ASSETS = ROOT / "assets"
BG, PANEL, BORDER, TEXT, MUTED = "#0A1820", "#10232C", "#21404D", "#E7F1F3", "#8BA6AF"
MINT, FLASH, RED, BLUE = "#6AFFA4", "#FFD166", "#FF5C61", "#5AB4FF"
METHODS = ["2023 rule, as shipped", "2023 rule, fixed input", "AR forecast", "ecHT"]
LABELS = {
    "2023 rule, as shipped": "2023 code\nas shipped",
    "2023 rule, fixed input": "2023 rule\ninput bug fixed",
    "AR forecast": "AR forecast\n(phastimate-style)",
    "ecHT": "ecHT\n(NeuroBack 2026)",
}
COLORS = dict(zip(METHODS, [RED, MUTED, BLUE, MINT]))

_fonts = {f.name for f in font_manager.fontManager.ttflist}
FONT = next((f for f in ("Avenir Next", "Inter", "Helvetica Neue", "DejaVu Sans") if f in _fonts), "DejaVu Sans")
plt.rcParams.update({
    "font.family": FONT, "font.size": 11, "text.color": TEXT, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": BORDER, "axes.facecolor": BG,
    "figure.facecolor": BG, "savefig.facecolor": BG, "axes.titleweight": "semibold", "axes.titlesize": 13,
    "axes.spines.top": False, "axes.spines.right": False, "grid.color": BORDER, "grid.alpha": 0.6,
})


def _title(fig, title, sub=None):
    fig.text(0.04, 0.95, title, fontsize=17, weight="semibold", color=TEXT, va="top")
    if sub:
        fig.text(0.04, 0.885, sub, fontsize=10.5, color=MUTED, va="top")


def _subject(sid=4):
    path = fetch([sid], verbose=False)[0]
    x160, fs_in, ch = occipital_channel(path)
    x = resample(x160, fs_in, 250.0)
    iaf = individual_alpha_frequency(x, 250.0).freq
    return x, 250.0, iaf


# ---------------------------------------------------------------------------- benchmark
def fig_benchmark(res: dict, pooled: dict):
    rows = res["subjects"]
    fig = plt.figure(figsize=(13, 5.6))
    _title(fig, f"Where do the flashes land?  Real EEG, {res['n_subjects']} people",
           "Target = alpha peak (0°). Phase measured afterwards with a non-causal Hilbert transform. PhysioNet EEGMMIDB, eyes closed, Oz, "
           "streamed live in 4-sample (16 ms) chunks.")
    for i, m in enumerate(METHODS):
        ax = fig.add_axes([0.035 + i * 0.245, 0.13, 0.19, 0.56], projection="polar")
        ax.set_facecolor(PANEL)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        err = np.radians(pooled[m].astype(float))
        bins = np.linspace(-np.pi, np.pi, 37)
        h, _ = np.histogram(err, bins)
        h = h / h.sum()
        ax.bar(bins[:-1] + np.diff(bins) / 2, h, width=np.diff(bins), color=COLORS[m], alpha=0.9, edgecolor=BG, linewidth=0.5)
        ax.set_ylim(0, 0.16)
        ax.set_yticks([])
        ax.set_xticks(np.radians([0, 90, 180, 270]))
        ax.set_xticklabels(["peak", "", "trough", ""], fontsize=8.5, color=MUTED)
        ax.grid(color=BORDER, alpha=0.7)
        ax.spines["polar"].set_color(BORDER)
        med = np.median([r[m]["plv"] for r in rows])
        sd = np.median([r[m]["circ_sd_deg"] for r in rows])
        cx = 0.035 + i * 0.245 + 0.095
        fig.text(cx, 0.775, LABELS[m].replace("\n", " "), ha="center", color=COLORS[m] if m != METHODS[1] else TEXT,
                 fontsize=12.5, weight="semibold")
        fig.text(cx, 0.04, f"phase-locking {med:.2f}   ·   spread ±{sd:.0f}°", ha="center", color=TEXT, fontsize=11)
    fig.savefig(FIG / "benchmark-polar.png", dpi=160)
    plt.close(fig)


def fig_benchmark_subjects(res: dict):
    rows = res["subjects"]
    fig = plt.figure(figsize=(13, 5.6))
    _title(fig, "Better phase locking in every one of 109 people", "Left: phase-locking value (1 = every flash at the same phase) per person. "
           "Right: locking vs alpha strength at the moment of the flash.")
    ax = fig.add_axes([0.06, 0.16, 0.5, 0.62])
    rng = np.random.default_rng(0)
    vals = [np.array([r[m]["plv"] for r in rows]) for m in METHODS]
    for i, (m, v) in enumerate(zip(METHODS, vals)):
        ax.scatter(i + rng.uniform(-0.12, 0.12, len(v)), v, s=11, color=COLORS[m], alpha=0.8, zorder=2, linewidths=0)
        ax.plot([i - 0.25, i + 0.25], [np.median(v)] * 2, color=TEXT, lw=2.5, zorder=3)
        ax.text(i, 1.03, f"{np.median(v):.2f}", ha="center", color=TEXT, fontsize=11, weight="semibold")
    ax.set_xticks(range(4))
    ax.set_xticklabels([LABELS[m] for m in METHODS], fontsize=9.5)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("phase-locking value")
    ax.grid(axis="y")
    better = int(np.sum(vals[3] > vals[1]))
    ax.text(2.5, 0.06, f"ecHT > 2023 rule in {better}/{len(rows)} people", ha="center", color=MUTED, fontsize=9.5)

    ax2 = fig.add_axes([0.66, 0.16, 0.31, 0.62])
    q = np.arange(4)
    for m in METHODS:
        arr = np.array([[np.nan if v is None else v for v in r[m]["plv_by_quartile"]] for r in rows])
        ax2.plot(q, np.nanmedian(arr, axis=0), "-o", color=COLORS[m], lw=2.2, ms=6, label=LABELS[m].replace("\n", " "))
    ax2.set_xticks(q)
    ax2.set_xticklabels(["weakest\n25%", "", "", "strongest\n25%"])
    ax2.set_xlabel("alpha amplitude at the flash (within person)")
    ax2.set_ylabel("median phase-locking value")
    ax2.set_ylim(0, 1)
    ax2.grid(axis="y")
    ax2.legend(frameon=False, fontsize=8.5, loc="lower right", bbox_to_anchor=(1.0, 0.18), labelcolor=TEXT)
    fig.savefig(FIG / "benchmark-subjects.png", dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------------------- 2023 diagnostics
def fig_legacy_filter():
    fs, f0 = 250.0, 10.0
    b, a = signal.iirfilter(2, [f0 - 1, f0 + 1], btype="band", ftype="butter", fs=fs)
    f = np.linspace(8, 12, 400)
    _, h = signal.freqz(b, a, worN=f, fs=fs)
    _, gd = signal.group_delay((b, a), w=f, fs=fs)
    fig = plt.figure(figsize=(12, 4.6))
    _title(fig, "Why the 2023 phase detector drifted", "Its band-pass (PAF ± 1 Hz, causal Butterworth) shifts phase by ±90° "
           "when alpha is only 1 Hz away from the calibrated frequency, and delays the signal by ~0.2 s.")
    ax = fig.add_axes([0.06, 0.14, 0.4, 0.62])
    ax.plot(f - f0, np.degrees(np.angle(h)), color=RED, lw=2.5)
    ax.axhline(0, color=BORDER)
    ax.axvspan(-0.67, 0.67, color=FLASH, alpha=0.12)
    ax.text(0, -120, "2023 PAF grid could be\noff by up to ±0.67 Hz", ha="center", color=FLASH, fontsize=9)
    ax.set_xlabel("alpha frequency minus filter centre (Hz)")
    ax.set_ylabel("phase error introduced (°)")
    ax.set_ylim(-150, 150)
    ax.grid()
    ax2 = fig.add_axes([0.56, 0.14, 0.4, 0.62])
    ax2.plot(f - f0, gd / fs * 1000, color=RED, lw=2.5)
    ax2.axhline(100, color=MUTED, ls="--", lw=1)
    ax2.text(-1.9, 108, "one alpha cycle (100 ms)", color=MUTED, fontsize=9)
    ax2.set_xlabel("alpha frequency minus filter centre (Hz)")
    ax2.set_ylabel("group delay (ms)")
    ax2.set_ylim(0, 320)
    ax2.grid()
    fig.savefig(FIG / "legacy-filter.png", dpi=160)
    plt.close(fig)


def fig_jitter_budget():
    jit = np.linspace(0, 12, 200)
    fig = plt.figure(figsize=(12, 4.6))
    _title(fig, "Timing is phase", "Each millisecond of timing error is 2.9–4.7° of alpha phase (8–13 Hz). "
           "Points: jitter measured by Knierim et al. (2023), Sensors 23:4559.")
    ax = fig.add_axes([0.06, 0.14, 0.58, 0.62])
    for f, c in ((8, BLUE), (10, MINT), (13, FLASH)):
        ax.plot(jit, 360 * f * jit / 1000, color=c, lw=2.4, label=f"{f} Hz alpha")
    for x, lab, off in ((2.10, "OpenBCI Cyton, FTDI fix,\n250 Hz: 2.1 ms", (3.4, 4)),
                        (1.17, "research amplifier\n(Smarting Mobi): 1.2 ms", (0.4, 26))):
        y = 360 * 10 * x / 1000
        ax.scatter([x], [y], color=TEXT, s=40, zorder=3)
        ax.annotate(lab, (x, y), off, color=TEXT, fontsize=9, arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.set_xlabel("timing jitter (ms)")
    ax.set_ylabel("phase error (°)")
    ax.legend(frameon=False, labelcolor=TEXT, loc="upper left")
    ax.grid()
    ax.text(1.04, 0.95, "Before you trust a closed loop", transform=ax.transAxes, color=TEXT, weight="semibold", fontsize=11)
    tips = ["Set the FTDI latency timer to 1 ms: default", "  buffering adds ~330 ms lag (Knierim 2023),",
            "  over three alpha cycles", "Measure your output latency with a photodiode", "  and pass it as --latency-ms",
            "NeuroBack uses every sample, refines each flash", "  time per chunk and schedules it to <1 ms"]
    for i, t in enumerate(tips):
        ax.text(1.04, 0.83 - i * 0.1, ("• " if not t.startswith("  ") else "   ") + t.strip(), transform=ax.transAxes,
                color=MUTED, fontsize=9.5)
    fig.savefig(FIG / "jitter-budget.png", dpi=160)
    plt.close(fig)


def fig_legacy_audit(csv_path: Path):
    raw = Path(csv_path).read_text().replace(",", ".")
    X = np.loadtxt(raw.splitlines(), delimiter="\t")
    ts = X[:, 30] - X[0, 30]
    u = np.unique(ts)
    gaps = np.where(np.diff(u) > 0.05)[0]
    bounds = [u[0], *u[gaps + 1]]
    blk = np.searchsorted(bounds, ts, side="right") - 1
    fig = plt.figure(figsize=(12, 4.8))
    _title(fig, "The 2023 recording bug, from the original file",
           "Every save re-wrote the whole buffer (np.delete's result was discarded), so each 20 s delay block filled ~12,900 rows. "
           "The analysis read 5,000 rows per delay.")
    ax = fig.add_axes([0.07, 0.14, 0.88, 0.6])
    cols = [MINT, BLUE, FLASH]
    for b in range(3):
        m = blk == b
        ax.scatter(np.where(m)[0], ts[m], s=1, color=cols[b], label=f"delay block {b} (actual data)")
    for i in range(3):
        ax.axvspan(i * 5000, (i + 1) * 5000, ymin=0.92, ymax=1.0, color=cols[i], alpha=0.85)
        ax.text(i * 5000 + 2500, ts.max() * 1.035, f"read as delay {i}", ha="center", color=BG, fontsize=8.5, weight="semibold")
    ax.set_xlabel("row in EV-EEG*.csv")
    ax.set_ylabel("sample timestamp (s)")
    ax.set_ylim(0, ts.max() * 1.09)
    ax.legend(frameon=False, labelcolor=TEXT, loc="lower right", markerscale=8)
    ax.grid()
    fig.savefig(FIG / "legacy-audit.png", dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------------------- evidence
# Effect sizes oriented so that positive = benefit. SMD / Hedges g / Cohen d with 95% CI.
EVIDENCE = [
    # label, estimate, lo, hi, group, source
    ("ADHD, all protocols, probably-blinded raters", 0.04, -0.10, 0.18, "sham", "Westwood et al. 2025, JAMA Psychiatry"),
    ("ADHD, standard protocols, probably-blinded", 0.21, 0.02, 0.40, "sham", "Westwood et al. 2025, JAMA Psychiatry"),
    ("Healthy attention vs sham", 0.18, -0.18, 0.53, "sham", "Kimura et al. 2024, Imaging Neuroscience"),
    ("Stroke motor BCI vs sham BCI", 0.22, -0.08, 0.52, "sham", "Qin et al. 2026, Cochrane CD015065"),
    ("PTSD, EEG neurofeedback vs sham (1 trial)", 0.43, -0.23, 1.09, "sham", "Berman et al. 2025, Front Neurosci"),
    ("Closed-loop sleep stimulation, memory", 0.14, -0.14, 0.42, "sham", "Harlow et al. 2023, Front Sleep"),
    ("Healthy attention vs no intervention", 0.36, 0.003, 0.73, "passive", "Kimura et al. 2024, Imaging Neuroscience"),
    ("Healthy working memory (mostly no-feedback controls)", 0.56, 0.31, 0.81, "passive", "Yeh et al. 2021, Front Hum Neurosci"),
    ("Sport performance (mixed controls)", 0.78, 0.49, 1.07, "passive", "Yu et al. 2025, Scand J Med Sci Sports"),
    ("PTSD, EEG neurofeedback vs passive controls", 1.32, 0.66, 1.99, "passive", "Berman et al. 2025, Front Neurosci"),
]


def fig_evidence():
    fig = plt.figure(figsize=(14, 6.6))
    _title(fig, "The stronger the control, the smaller the effect",
           "Pooled effect sizes from recent meta-analyses (positive = benefit, 95% CI). Sham controls isolate what is specific to the "
           "brain feedback.")
    ax = fig.add_axes([0.335, 0.1, 0.33, 0.7])
    n = len(EVIDENCE)
    ax.set_ylim(-0.5, n + 0.4)
    ax.set_xlim(-0.4, 2.1)
    for i, (lab, est, lo, hi, grp, src) in enumerate(EVIDENCE):
        y = n - 1 - i + (0.6 if grp == "sham" else 0)
        c = MINT if grp == "sham" else FLASH
        ax.plot([lo, hi], [y, y], color=c, lw=2.2, solid_capstyle="round")
        ax.scatter([est], [y], s=60, color=c, zorder=3, edgecolor=BG)
        yy = ax.transData.transform((0, y))[1]
        yf = fig.transFigure.inverted().transform((0, yy))[1]
        fig.text(0.325, yf, lab, ha="right", va="center", color=TEXT, fontsize=10)
        fig.text(0.675, yf, f"{est:.2f}  [{lo:.2f}, {hi:.2f}]", ha="left", va="center", color=TEXT, fontsize=9)
        fig.text(0.765, yf, src, ha="left", va="center", color=MUTED, fontsize=8.5)
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_yticks([])
    ax.set_xlabel("standardised effect size")
    ax.grid(axis="x")
    for y, lab, c in ((n + 0.05, "SHAM-CONTROLLED", MINT), (3.9, "WAITLIST / NO-FEEDBACK / MIXED CONTROLS", FLASH)):
        yf = fig.transFigure.inverted().transform(ax.transData.transform((0, y)))[1]
        fig.text(0.325, yf, lab, ha="right", va="center", color=c, fontsize=9, weight="semibold")
    fig.savefig(FIG / "evidence-map.png", dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------------------- hero + demo
def _closed_loop_on(x, fs, iaf):
    truth, amp, alpha = offline_phase(x, fs, iaf)
    t = run_offline(x, fs, ClosedLoop(fs, EcHT(fs, iaf), f0=iaf, target_deg=0), chunk=4)
    return truth, alpha, t


def fig_hero():
    x, fs, iaf = _subject(4)
    truth, alpha, trig = _closed_loop_on(x, fs, iaf)
    t0, dur = 20.0, 3.2
    tx = np.arange(len(x)) / fs
    m = (tx >= t0) & (tx < t0 + dur)
    tt = tx[m]
    k = 30 / np.max(np.abs(alpha[m]))  # alpha band spans -80..-20
    yoff = -50
    fig = plt.figure(figsize=(12.8, 6.4), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(t0 - 0.05, t0 + dur)
    ax.set_ylim(-100, 75)
    ax.axis("off")
    raw = np.clip(x[m] * k * 0.6 + yoff, -97, -4)
    ax.plot(tt, raw, color=MUTED, lw=0.8, alpha=0.22)
    for w, a in ((10, 0.05), (5, 0.10), (2.2, 1.0)):
        ax.plot(tt, alpha[m] * k + yoff, color=MINT, lw=w, alpha=a, solid_capstyle="round")
    ft = trig[(trig >= t0) & (trig < t0 + dur)]
    fy = np.interp(ft, tx, alpha) * k + yoff
    for f, y in zip(ft, fy):
        for top, a in ((y + 8, 0.35), (y + 16, 0.18), (y + 26, 0.08)):
            ax.plot([f, f], [y, top], color=FLASH, lw=1.4, alpha=a, solid_capstyle="round")
        for sz, a in ((520, 0.07), (190, 0.2), (36, 1.0)):
            ax.scatter([f], [y], s=sz, color=FLASH, alpha=a, linewidths=0, zorder=4)
    ax.text(t0 + 0.08, 50, "NeuroBack", fontsize=66, weight="bold", color=TEXT, va="center")
    ax.text(t0 + 0.1, 27, "Closed-loop light stimulation, locked to your alpha rhythm", fontsize=21, color=TEXT, va="center")
    ax.text(t0 + 0.1, 14, "OpenBCI Cyton  ·  endpoint-corrected Hilbert transform  ·  109-person real-EEG benchmark  ·  PyQt6 app",
            fontsize=12.5, color=MUTED, va="center")
    ax.text(t0 + dur - 0.06, -96, "Real EEG, PhysioNet S004, Oz.  Yellow: flashes scheduled causally at the alpha peak.",
            fontsize=9.5, color=MUTED, ha="right", va="bottom")
    fig.savefig(ASSETS / "hero.png", dpi=100)
    plt.close(fig)


def demo_gif(seconds=6.0, fps=12):
    from matplotlib.animation import FuncAnimation, PillowWriter

    x, fs, iaf = _subject(4)
    truth, alpha, trig = _closed_loop_on(x, fs, iaf)
    start, win = 30.0, 2.5
    tx = np.arange(len(x)) / fs
    fig = plt.figure(figsize=(9.6, 3.6), dpi=84)
    ax = fig.add_axes([0.03, 0.17, 0.6, 0.66])
    axp = fig.add_axes([0.69, 0.1, 0.27, 0.7], projection="polar")
    fig.text(0.03, 0.92, "Closed loop on real EEG", color=TEXT, fontsize=13, weight="semibold")
    fig.text(0.03, 0.865, "grey: raw Oz · mint: alpha · yellow: flash, aimed at the peak", color=MUTED, fontsize=9)
    raw_l, = ax.plot([], [], color=MUTED, lw=0.8, alpha=0.5)
    al_l, = ax.plot([], [], color=MINT, lw=2)
    fl = ax.scatter([], [], s=60, color=FLASH, zorder=4)
    ax.set_ylim(-60, 60)
    ax.set_yticks([])
    ax.set_xlabel("time (s)")
    axp.set_theta_zero_location("N")
    axp.set_theta_direction(-1)
    axp.set_facecolor(PANEL)
    axp.set_yticks([])
    axp.set_ylim(0, 1)
    axp.set_xticks(np.radians([0, 90, 180, 270]))
    axp.set_xticklabels(["peak", "", "trough", ""], color=MUTED, fontsize=8)
    axp.spines["polar"].set_color(BORDER)
    axp.add_patch(Wedge((0, 0), 1, 70, 110, transform=axp.transData._b, color=MINT, alpha=0.15))
    needle, = axp.plot([], [], color=TEXT, lw=2.5)
    hits = axp.scatter([], [], s=28, color=FLASH, alpha=0.85)
    ptxt = fig.text(0.825, 0.92, "", color=TEXT, ha="center", fontsize=10)
    n = int(seconds * fps)

    def frame(k):
        t_end = start + win + k / fps
        m = (tx > t_end - win) & (tx <= t_end)
        raw_l.set_data(tx[m], x[m] * 0.8)
        al_l.set_data(tx[m], alpha[m])
        ax.set_xlim(t_end - win, t_end)
        f = trig[(trig > t_end - win) & (trig <= t_end)]
        fl.set_offsets(np.c_[f, np.interp(f, tx, alpha)] if len(f) else np.empty((0, 2)))
        ph = np.interp(t_end * fs, np.arange(len(truth)), np.unwrap(truth))
        needle.set_data([ph, ph], [0, 0.75])
        past = trig[(trig > start) & (trig <= t_end)]
        hp = phase_at(past, truth, fs)
        hits.set_offsets(np.c_[hp, np.full(len(hp), 0.86)] if len(hp) else np.empty((0, 2)))
        if len(hp) > 3:
            ptxt.set_text(f"phase-locking {plv(hp):.2f}  ({len(hp)} flashes)")
        return raw_l, al_l, fl, needle, hits, ptxt

    anim = FuncAnimation(fig, frame, frames=n, blit=False)
    anim.save(ASSETS / "demo.gif", writer=PillowWriter(fps=fps))
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--legacy-csv", default=None)
    ap.add_argument("--skip-gif", action="store_true")
    a = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    res = json.loads((Path(a.results) / "benchmark.json").read_text())
    pooled = dict(np.load(Path(a.results) / "pooled_errors.npz"))
    fig_benchmark(res, pooled)
    fig_benchmark_subjects(res)
    fig_legacy_filter()
    fig_jitter_budget()
    fig_evidence()
    fig_hero()
    if a.legacy_csv:
        fig_legacy_audit(Path(a.legacy_csv))
    if not a.skip_gif:
        demo_gif()
    print("figures written to", FIG, "and", ASSETS)


if __name__ == "__main__":
    main()
