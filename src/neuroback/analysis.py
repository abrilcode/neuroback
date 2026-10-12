"""Circular statistics and the phase-dependence test used after a phase sweep."""

from __future__ import annotations

import math

import numpy as np


def wrap(a):
    """Wrap angles to (-pi, pi]."""
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def plv(errors_rad) -> float:
    """Phase-locking value (mean resultant length) of phase errors, 0..1."""
    e = np.asarray(errors_rad)
    return float(np.abs(np.mean(np.exp(1j * e)))) if e.size else float("nan")


def circ_mean_deg(errors_rad) -> float:
    e = np.asarray(errors_rad)
    return float(np.degrees(np.angle(np.mean(np.exp(1j * e))))) if e.size else float("nan")


def circ_sd_deg(errors_rad) -> float:
    """Circular standard deviation sqrt(-2 ln R), in degrees."""
    r = plv(errors_rad)
    return float(np.degrees(math.sqrt(-2 * math.log(r)))) if 0 < r <= 1 else float("inf")


def phase_at(times_s, true_phase, fs: float):
    """Interpolate an offline phase trace at arbitrary times (seconds)."""
    unwrapped = np.unwrap(true_phase)
    idx = np.asarray(times_s) * fs
    return wrap(np.interp(idx, np.arange(len(unwrapped)), unwrapped))


def cosine_fit(phases_rad, values):
    """Least-squares fit values ~ c + a*cos(phase - phi). Returns (c, a, phi_rad, r2)."""
    p = np.asarray(phases_rad, dtype=float)
    v = np.asarray(values, dtype=float)
    X = np.column_stack([np.ones_like(p), np.cos(p), np.sin(p)])
    beta, *_ = np.linalg.lstsq(X, v, rcond=None)
    c, bc, bs = beta
    resid = v - X @ beta
    ss_tot = float(np.sum((v - v.mean()) ** 2)) or 1e-12
    return float(c), float(np.hypot(bc, bs)), float(np.arctan2(bs, bc)), 1 - float(np.sum(resid**2)) / ss_tot


def phase_dependence_test(phases_rad, values, n_perm: int = 5000, seed: int = 0):
    """Permutation test for a 1-cycle (cosine) dependence of ``values`` on stimulation phase.

    Shuffles phase labels across blocks; the statistic is the fitted cosine amplitude.
    Returns dict with amplitude, preferred phase (deg) and p-value.
    """
    rng = np.random.default_rng(seed)
    _, amp, phi, r2 = cosine_fit(phases_rad, values)
    null = np.empty(n_perm)
    p = np.asarray(phases_rad)
    for i in range(n_perm):
        null[i] = cosine_fit(rng.permutation(p), values)[1]
    pval = (1 + np.sum(null >= amp)) / (n_perm + 1)
    return {"amplitude": amp, "preferred_deg": math.degrees(phi) % 360, "r2": r2, "p": float(pval)}


def bootstrap_ci(values, n_boot: int = 5000, ci: float = 0.95, seed: int = 0):
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    means = rng.choice(v, size=(n_boot, v.size), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    return float(v.mean()), float(lo), float(hi)
