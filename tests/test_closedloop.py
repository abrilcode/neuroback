import numpy as np
import pytest

from neuroback.analysis import circ_mean_deg, phase_at
from neuroback.closedloop import ClosedLoop, run_offline
from neuroback.dsp import offline_phase
from neuroback.phase import EcHT

FS = 250.0


@pytest.mark.parametrize("target", [0, 90, 180, 270])
def test_hits_requested_target_phase(target):
    t = np.arange(0, 30, 1 / FS)
    rng = np.random.default_rng(0)
    x = np.cos(2 * np.pi * 10 * t) + 0.2 * rng.normal(size=t.size)
    truth, _, _ = offline_phase(x, FS, 10.0)
    trig = run_offline(x, FS, ClosedLoop(FS, EcHT(FS, 10.0), f0=10.0, target_deg=target), chunk=4)
    err = circ_mean_deg(phase_at(trig, truth, FS) - np.radians(target))
    assert abs(err) < 15


def test_at_most_one_stimulus_per_cycle():
    t = np.arange(0, 20, 1 / FS)
    x = np.cos(2 * np.pi * 10 * t)
    trig = run_offline(x, FS, ClosedLoop(FS, EcHT(FS, 10.0), f0=10.0), chunk=4)
    assert np.min(np.diff(trig)) > 0.05
    assert 9 < len(trig) / 20 <= 10.05


def test_latency_is_compensated():
    t = np.arange(0, 20, 1 / FS)
    x = np.cos(2 * np.pi * 10 * t)
    truth, _, _ = offline_phase(x, FS, 10.0)
    latency = 0.030
    trig = run_offline(x, FS, ClosedLoop(FS, EcHT(FS, 10.0), f0=10.0, latency_s=latency), chunk=4)
    arrival = trig + latency  # when the light actually turns on
    assert abs(circ_mean_deg(phase_at(arrival[arrival < 19.9], truth, FS))) < 15


def test_amplitude_gate_suppresses_stimulation_without_alpha():
    rng = np.random.default_rng(1)
    x = 0.01 * rng.normal(size=int(10 * FS))
    loop = ClosedLoop(FS, EcHT(FS, 10.0), f0=10.0, amp_threshold=1.0)
    assert len(run_offline(x, FS, loop, chunk=4)) == 0
