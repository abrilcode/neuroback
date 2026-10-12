import numpy as np
from scipy import signal

from neuroback.dsp import individual_alpha_frequency, offline_phase
from neuroback.simulate import alpha_eeg

FS = 250.0


def test_iaf_resolves_off_grid_frequency():
    x = alpha_eeg(120, FS, iaf=9.6, seed=1)
    peak = individual_alpha_frequency(x, FS)
    assert peak.found
    assert abs(peak.freq - 9.6) < 0.25


def test_2023_welch_settings_could_not_resolve_iaf():
    """Regression note: nperseg=187 at 250 Hz gives 1.34 Hz bins (8.02, 9.36, 10.70, 12.03 Hz)."""
    f = np.fft.rfftfreq(int(FS * 0.75), 1 / FS)
    assert np.allclose(f[(f > 7.5) & (f < 12.5)], [8.021, 9.358, 10.695, 12.032], atol=1e-3)


def test_offline_phase_cosine_convention():
    t = np.arange(0, 10, 1 / FS)
    x = np.cos(2 * np.pi * 10 * t)
    ph, amp, _ = offline_phase(x, FS, 10.0)
    mid = slice(500, 2000)
    err = np.angle(np.exp(1j * (ph[mid] - 2 * np.pi * 10 * t[mid])))
    assert np.max(np.abs(err)) < np.radians(3)
