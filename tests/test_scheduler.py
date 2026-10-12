import os
import time

import numpy as np

# Shared CI runners have noisy timers; locally flashes land within ~1 ms.
TOL_S = 0.015 if os.environ.get("CI") else 0.003

from neuroback.closedloop import OpenLoop, RandomPhase
from neuroback.stimulators import TriggerScheduler, VirtualStimulator


def test_tentative_deadlines_are_refined_and_fire_on_time():
    stim = VirtualStimulator()
    sched = TriggerScheduler(stim)
    try:
        errors = []
        for _ in range(5):
            deadline = time.perf_counter() + 0.05
            sched.tentative(deadline + 0.02)  # first estimate
            sched.tentative(deadline)  # refined estimate replaces it
            time.sleep(0.12)
            errors.append(stim.times[-1] - deadline)
        assert len(stim.times) == 5
        assert max(abs(e) for e in errors) < TOL_S
    finally:
        sched.stop()


def test_committed_deadline_survives_a_new_tentative_one():
    stim = VirtualStimulator()
    sched = TriggerScheduler(stim)
    now = time.perf_counter()
    sched.commit(now + 0.03)
    sched.tentative(now + 0.08)  # next cycle's estimate must not overwrite the committed one
    time.sleep(0.15)
    sched.stop()
    assert len(stim.times) == 2


def test_committing_an_already_fired_tentative_does_not_double_flash():
    stim = VirtualStimulator()
    sched = TriggerScheduler(stim)
    d = time.perf_counter() + 0.03
    sched.tentative(d)
    time.sleep(0.06)
    sched.commit(d)  # the engine commits it late
    time.sleep(0.05)
    sched.stop()
    assert len(stim.times) == 1


def test_cancel_prevents_flash():
    stim = VirtualStimulator()
    sched = TriggerScheduler(stim)
    sched.commit(time.perf_counter() + 0.05)
    sched.cancel()
    time.sleep(0.1)
    sched.stop()
    assert stim.times == []


def test_control_conditions_match_alpha_rate():
    for eng in (OpenLoop(250.0, 10.0), RandomPhase(250.0, 10.0, seed=0)):
        fired = []
        for _ in range(2500 // 5):
            fired += eng.push(np.zeros(5))
        assert 9 <= len(fired) / 10 <= 11
