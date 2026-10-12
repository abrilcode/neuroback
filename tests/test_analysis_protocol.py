from collections import Counter

import numpy as np

from neuroback.analysis import cosine_fit, phase_dependence_test
from neuroback.protocol import SweepConfig


def test_cosine_fit_recovers_preferred_phase():
    p = np.radians(np.repeat([0, 90, 180, 270], 6))
    v = 5 + 2 * np.cos(p - np.radians(90))
    c, a, phi, r2 = cosine_fit(p, v)
    assert abs(np.degrees(phi) - 90) < 1 and abs(a - 2) < 1e-6 and r2 > 0.99


def test_permutation_test_separates_effect_from_null():
    rng = np.random.default_rng(0)
    p = np.radians(np.repeat([0, 90, 180, 270], 8))
    strong = 1 + 0.8 * np.cos(p) + 0.2 * rng.normal(size=p.size)
    null = 1 + 0.2 * rng.normal(size=p.size)
    assert phase_dependence_test(p, strong, n_perm=999)["p"] < 0.01
    assert phase_dependence_test(p, null, n_perm=999)["p"] > 0.05


def test_sweep_is_block_randomised_and_balanced():
    cfg = SweepConfig(repeats=4, seed=1)
    order = cfg.schedule()
    counts = Counter(c.label for c in order)
    assert set(counts.values()) == {4} and len(counts) == 6
    blocks = [order[i : i + 6] for i in range(0, len(order), 6)]
    assert all(len({c.label for c in b}) == 6 for b in blocks)
    assert [c.label for c in order[:6]] != [c.label for c in cfg.conditions()]
