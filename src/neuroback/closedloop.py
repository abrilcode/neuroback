"""Closed-loop engine: turns streaming EEG into stimulation times at a target alpha phase."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

TWO_PI = 2 * math.pi


@dataclass
class LoopStats:
    estimates: int = 0
    gated: int = 0
    fired: list[float] = field(default_factory=list)


class ClosedLoop:
    """Schedule one stimulus per alpha cycle at ``target_deg``.

    Every incoming chunk is appended to a ring buffer (all samples; the 2023 loop dropped
    all but the last sample of each chunk). The estimator returns the phase at the newest
    sample; the engine projects forward at the individual alpha frequency to the next
    moment the target phase occurs, minus the known output ``latency_s``. A pending
    stimulus keeps being refined with each new chunk until it is closer than
    ``commit_s``, after which it is handed to the hardware scheduler.

    Times are in seconds since the first sample (sample clock), so the same engine runs
    offline on recordings and live on a board.
    """

    def __init__(
        self,
        fs: float,
        estimator,
        f0: float,
        target_deg: float = 0.0,
        latency_s: float = 0.0,
        commit_s: float = 0.004,
        refractory: float = 0.6,
        amp_threshold: float | None = None,
    ):
        self.fs = fs
        self.est = estimator
        self.f0 = f0
        self.target = math.radians(target_deg) % TWO_PI
        self.latency_s = latency_s
        self.commit_s = commit_s
        self.refractory_s = refractory / f0
        self.amp_threshold = amp_threshold
        self.buf = np.zeros(estimator.window)
        self.n_seen = 0
        self.pending: float | None = None
        self.last_fired = -math.inf
        self.stats = LoopStats()

    def set_target(self, target_deg: float) -> None:
        self.target = math.radians(target_deg) % TWO_PI
        self.pending = None

    def push(self, chunk: np.ndarray) -> list[float]:
        """Add samples; return the stimulus times committed during this chunk."""
        chunk = np.asarray(chunk, dtype=float)
        if len(chunk) == 0:
            return []
        if len(chunk) >= len(self.buf):
            self.buf[:] = chunk[-len(self.buf) :]
        else:
            self.buf = np.roll(self.buf, -len(chunk))
            self.buf[-len(chunk) :] = chunk
        self.n_seen += len(chunk)
        t_now = (self.n_seen - 1) / self.fs

        fired = []
        if self.pending is not None and self.pending <= t_now + self.commit_s:
            fired.append(self.pending)
            self.last_fired = self.pending
            self.stats.fired.append(self.pending)
            self.pending = None

        if self.n_seen < len(self.buf):
            return fired

        e = self.est.estimate(self.buf)
        self.stats.estimates += 1
        if self.amp_threshold is not None and e.amplitude < self.amp_threshold:
            self.stats.gated += 1
            self.pending = None
            return fired

        wait = ((self.target - e.phase) % TWO_PI) / (TWO_PI * self.f0) - self.latency_s
        period = 1 / self.f0
        while wait < self.commit_s or t_now + wait < self.last_fired + self.refractory_s:
            wait += period
        self.pending = t_now + wait
        return fired

    def flush(self) -> list[float]:
        """Commit a still-pending stimulus at the end of a recording."""
        if self.pending is None:
            return []
        t = self.pending
        self.pending = None
        self.stats.fired.append(t)
        return [t]


class OpenLoop:
    """Control condition: flashes at the individual alpha frequency, ignoring phase."""

    def __init__(self, fs: float, f0: float):
        self.fs, self.period = fs, 1 / f0
        self.n_seen = 0
        self.pending: float | None = None

    def push(self, chunk) -> list[float]:
        self.n_seen += len(chunk)
        t_now = (self.n_seen - 1) / self.fs
        fired = []
        if self.pending is None:
            self.pending = t_now + self.period
        while self.pending <= t_now + 0.004:
            fired.append(self.pending)
            self.pending += self.period
        return fired


class RandomPhase(OpenLoop):
    """Control condition: same mean flash rate as the closed loop, random phase per cycle."""

    def __init__(self, fs: float, f0: float, seed: int | None = None):
        super().__init__(fs, f0)
        self.rng = np.random.default_rng(seed)

    def push(self, chunk) -> list[float]:
        self.n_seen += len(chunk)
        t_now = (self.n_seen - 1) / self.fs
        fired = []
        if self.pending is None:
            self.pending = t_now + self.period * self.rng.uniform(0.5, 1.5)
        while self.pending <= t_now + 0.004:
            fired.append(self.pending)
            self.pending += self.period * self.rng.uniform(0.5, 1.5)
        return fired


def run_offline(x: np.ndarray, fs: float, engine, chunk: int = 1) -> np.ndarray:
    """Stream a recording through ``engine`` in chunks; return all stimulus times."""
    times: list[float] = []
    for i in range(0, len(x), chunk):
        times.extend(engine.push(x[i : i + chunk]))
    if hasattr(engine, "flush"):
        times.extend(engine.flush())
    t = np.asarray(times)
    return t[t < len(x) / fs]
