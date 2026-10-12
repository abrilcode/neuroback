"""Pick estimator settings on SYNTHETIC data only (real EEG is held out for the benchmark)."""
import sys, numpy as np
sys.path.insert(0, "src")
from neuroback.simulate import alpha_eeg
from neuroback.dsp import offline_phase
from neuroback.phase import EcHT, ARForecast, LegacyZeroCrossing
from neuroback.closedloop import ClosedLoop, run_offline
from neuroback.analysis import phase_at, plv, circ_sd_deg, circ_mean_deg, wrap
fs=250
res={}
for seed in range(6):
    x = alpha_eeg(60, fs, iaf=10.0, seed=seed, alpha_uv=10, background_uv=8)
    ph, amp, _ = offline_phase(x, fs, 10.0)
    cfgs = {f"ecHT w{w} bw{bw}": (lambda w=w,bw=bw: EcHT(fs,10.0,bandwidth=bw,window_s=w)) for w in (0.5,1.0) for bw in (2.0,4.0)}
    cfgs.update({f"AR w{w}": (lambda w=w: ARForecast(fs,10.0,window_s=w)) for w in (0.5,1.0)})
    for name, mk in cfgs.items():
        eng = ClosedLoop(fs, mk(), f0=10.0, target_deg=0)
        t = run_offline(x, fs, eng, chunk=4)
        e = phase_at(t, ph, fs)
        res.setdefault(name, []).append((plv(e), circ_mean_deg(e), len(t)/60))
    for drop in (False, True):
        leg = LegacyZeroCrossing(fs, 10.0, delay_s=0, drop_extra_samples=drop)
        t = run_offline(x, fs, leg, chunk=4)
        e = phase_at(t, ph, fs)
        res.setdefault(f"legacy drop={drop}", []).append((plv(e), circ_mean_deg(e), len(t)/60))
for k,v in res.items():
    v=np.array(v); print(f"{k:22s} PLV {v[:,0].mean():.2f}  mean err {np.median(v[:,1]):7.1f} deg  rate {v[:,2].mean():.1f}/s")
