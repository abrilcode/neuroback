import numpy as np

from neuroback.analysis import phase_at, plv
from neuroback.dsp import offline_phase
from neuroback.safety import SCREENING_QUESTIONS
from neuroback.session import Session
from neuroback.sources import SimulatedAlpha

N_Q = len(SCREENING_QUESTIONS)


def make(tmp_path, iaf=10.2):
    return Session(SimulatedAlpha(realtime=False, iaf=iaf, seed=5), data_dir=tmp_path)


def run(s, seconds, step=5):
    for _ in range(int(seconds * s.fs / step)):
        s.tick(step)


def calibrated(tmp_path):
    s = make(tmp_path)
    assert s.command({"cmd": "create_participant", "age_band": "18-29", "answers": [False] * N_Q, "consent": True})["ok"]
    s.start_calibration(False, seconds=20)
    run(s, 21)
    s.start_calibration(True, seconds=20)
    run(s, 21)
    return s


def test_stimulation_is_locked_until_screening_consent_and_calibration(tmp_path):
    s = make(tmp_path)
    assert not s.command({"cmd": "start_stim"})["ok"]
    s.command({"cmd": "create_participant", "answers": [False] * (N_Q - 1) + [True], "consent": True})
    assert not s.cleared and not s.command({"cmd": "start_stim"})["ok"]
    s.command({"cmd": "create_participant", "answers": [False] * N_Q, "consent": True})
    assert s.cleared
    reply = s.command({"cmd": "start_stim"})
    assert not reply["ok"] and "eyes closed" in reply["message"]


def test_calibration_finds_iaf_and_reactivity(tmp_path):
    s = calibrated(tmp_path)
    assert abs(s.iaf - 10.2) < 0.3
    assert s.reactivity > 2
    snap = s.snapshot()
    assert snap["spectrum"]["f"][0] == 2.0 and len(snap["spectrum"]["ec"]) == len(snap["spectrum"]["f"])


def test_stimulation_locks_to_target_and_reports_accuracy(tmp_path):
    s = calibrated(tmp_path)
    assert s.command({"cmd": "start_stim", "target_deg": 0})["ok"]
    run(s, 12)
    snap = s.snapshot()
    assert snap["metrics"]["plv"] > 0.6 and 7 < snap["metrics"]["rate"] < 11
    flashes = np.array(list(s.flash_times))
    h = np.fromiter(s.history, float)
    t0 = s.n_total / s.fs - len(h) / s.fs
    truth, _, _ = offline_phase(h, s.fs, s.iaf)
    f = flashes[(flashes > t0 + 1) & (flashes < s.n_total / s.fs - 1)]
    assert plv(phase_at(f - t0, truth, s.fs)) > 0.6


def test_emergency_stop_halts_flashes(tmp_path):
    s = calibrated(tmp_path)
    s.start_stimulation(0)
    run(s, 3)
    s.command({"cmd": "stop"})
    n = s.flash_count
    run(s, 3)
    assert s.mode == "idle" and s.flash_count == n


def test_sweep_runs_all_blocks_and_summarises(tmp_path):
    s = calibrated(tmp_path)
    assert s.command({"cmd": "start_sweep", "demo_timing": True})["ok"]
    run(s, 6 * 2 * 6 + 2)
    res = s.snapshot()["results"]
    assert res["n_blocks"] == 12 and len(res["labels"]) == 6 and 0 < res["p"] <= 1


def test_save_and_snapshot_have_no_identifying_fields(tmp_path):
    s = calibrated(tmp_path)
    s.start_stimulation(90)
    run(s, 2)
    assert "session" in s.command({"cmd": "save"})["message"]
    snap = s.snapshot()
    assert set(snap["participants"][0]) == {"pid", "age_band", "cleared"}
