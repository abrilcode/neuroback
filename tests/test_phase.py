import numpy as np
import pytest

from neuroback.analysis import phase_at, plv
from neuroback.closedloop import ClosedLoop, run_offline
from neuroback.dsp import offline_phase
from neuroback.phase import ARForecast, EcHT, LegacyZeroCrossing
from neuroback.simulate import alpha_eeg

FS = 250.0


@pytest.mark.parametrize("cls", [EcHT, ARForecast])
def test_endpoint_phase_on_clean_sine(cls):
    est = cls(FS, 10.0)
    t = np.arange(est.window * 4) / FS
    errs = []
    for phi0 in np.linspace(0, 2 * np.pi, 12, endpoint=False):
        x = np.cos(2 * np.pi * 10 * t + phi0)
        true_end = 2 * np.pi * 10 * t[-1] + phi0
        errs.append(np.angle(np.exp(1j * (est.estimate(x).phase - true_end))))
    assert np.degrees(np.max(np.abs(errs))) < 12


@pytest.mark.parametrize("cls,min_plv", [(EcHT, 0.7), (ARForecast, 0.6)])
def test_closed_loop_locks_to_noisy_alpha(cls, min_plv):
    x = alpha_eeg(60, FS, iaf=10.0, seed=3)
    truth, _, _ = offline_phase(x, FS, 10.0)
    t = run_offline(x, FS, ClosedLoop(FS, cls(FS, 10.0), f0=10.0, target_deg=0), chunk=4)
    assert plv(phase_at(t, truth, FS)) > min_plv


def test_2023_chunk_bug_destroys_phase_locking():
    """Feeding only the last sample of each 4-sample chunk (the 2023 loop) leaves almost no locking."""
    x = alpha_eeg(60, FS, iaf=10.0, seed=3)
    truth, _, _ = offline_phase(x, FS, 10.0)
    shipped = run_offline(x, FS, LegacyZeroCrossing(FS, 10.0, drop_extra_samples=True), chunk=4)
    fixed = run_offline(x, FS, LegacyZeroCrossing(FS, 10.0, drop_extra_samples=False), chunk=4)
    assert plv(phase_at(shipped, truth, FS)) < 0.3 < plv(phase_at(fixed, truth, FS))
