"""Real-time (causal) alpha-phase estimators.

All estimators see only past samples and return the phase at the most recent sample,
in the cosine convention: 0 = peak, +-pi = trough, -pi/2 = rising zero-crossing.

* ``EcHT``       endpoint-corrected Hilbert transform (Schreglmann et al., 2021).
* ``ARForecast`` zero-phase filter + autoregressive forward prediction, the approach
                 behind phastimate (Zrenner et al., 2018; 2020).
* ``LegacyZeroCrossing`` the 2023 NeuroBack rule (causal IIR band-pass, rising
  zero-crossing + fixed delay), kept so it can be benchmarked against the new ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import linalg, signal


@dataclass(frozen=True)
class PhaseEstimate:
    phase: float  # radians at the last sample
    amplitude: float  # same units as the input


class EcHT:
    """Endpoint-corrected Hilbert transform.

    The analytic signal of the window is computed in the frequency domain and multiplied
    by the response of a causal 2nd-order band-pass centred on ``f0``. The causal filter
    removes the Gibbs distortion that makes the plain Hilbert transform unreliable at the
    window's end, which is exactly where a closed loop needs the phase.
    """

    name = "ecHT"

    def __init__(self, fs: float, f0: float, bandwidth: float = 4.0, window_s: float = 0.5):
        self.fs = fs
        self.f0 = f0
        self.n = int(round(window_s * fs))
        b, a = signal.butter(1, [f0 - bandwidth / 2, f0 + bandwidth / 2], btype="band", fs=fs)
        freqs = np.fft.fftfreq(self.n, d=1 / fs)
        _, h = signal.freqz(b, a, worN=np.abs(freqs), fs=fs)
        analytic = np.zeros(self.n)
        analytic[0] = 1.0
        analytic[1 : (self.n + 1) // 2] = 2.0
        if self.n % 2 == 0:
            analytic[self.n // 2] = 1.0
        self._kernel = analytic * h

    @property
    def window(self) -> int:
        return self.n

    def estimate(self, x: np.ndarray) -> PhaseEstimate:
        x = np.asarray(x[-self.n :], dtype=float)
        z = np.fft.ifft(np.fft.fft(x - x.mean()) * self._kernel)
        return PhaseEstimate(float(np.angle(z[-1])), float(np.abs(z[-1])))


class ARForecast:
    """Zero-phase FIR band-pass + autoregressive forecast across the filter edge.

    The zero-phase filter is accurate inside the window but distorted within half a filter
    length of its end, so those samples are discarded and replaced by an AR(p) prediction
    fitted to the clean part. A Hilbert transform centred on "now" over the forecast gives
    the current phase (the approach behind phastimate, Zrenner et al. 2018; 2020).
    """

    name = "AR forecast"

    def __init__(
        self,
        fs: float,
        f0: float,
        half_bw: float = 2.0,
        window_s: float = 0.5,
        filter_s: float = 0.132,
        hilbert_s: float = 0.256,
        order: int | None = None,
    ):
        self.fs = fs
        self.n = int(round(window_s * fs))
        numtaps = int(round(filter_s * fs)) | 1  # odd length, linear phase
        self.b = signal.firwin(numtaps, [f0 - half_bw, f0 + half_bw], pass_zero=False, fs=fs)
        self.edge = numtaps // 2
        self.hw = int(round(hilbert_s * fs))
        self.order = order or max(4, int(round(0.032 * fs)))

    @property
    def window(self) -> int:
        return self.n

    def estimate(self, x: np.ndarray) -> PhaseEstimate:
        x = np.asarray(x[-self.n :], dtype=float)
        y = signal.filtfilt(self.b, [1.0], x - x.mean())
        y = y[: len(y) - self.edge]
        p = self.order
        r = np.correlate(y, y, mode="full")[len(y) - 1 : len(y) + p] / len(y)
        try:
            coef = linalg.solve_toeplitz(r[:p], r[1 : p + 1])
        except (linalg.LinAlgError, ValueError):
            return PhaseEstimate(0.0, 0.0)
        ahead = self.edge + self.hw // 2
        ext = np.empty(len(y) + ahead)
        ext[: len(y)] = y
        for k in range(len(y), len(ext)):
            ext[k] = coef @ ext[k - p : k][::-1]
        seg = signal.hilbert(ext[-self.hw :])
        now = self.hw - 1 - self.hw // 2
        return PhaseEstimate(float(np.angle(seg[now])), float(np.abs(seg[now])))


class LegacyZeroCrossing:
    """The 2023 trigger rule, reproduced faithfully for the benchmark.

    Causal 2nd-order Butterworth band-pass at PAF +- 1 Hz (``signal.iirfilter(2, ...)``),
    trigger on each rising zero-crossing of the filtered signal, fire after a fixed delay.
    With ``drop_extra_samples=True`` it also reproduces the 2023 bug where only the last
    sample of each incoming chunk was fed to the filter.
    """

    name = "2023 zero-crossing"

    def __init__(self, fs: float, f0: float, delay_s: float = 0.0, drop_extra_samples: bool = False):
        self.fs = fs
        self.delay_s = delay_s
        self.drop = drop_extra_samples
        self.b, self.a = signal.iirfilter(2, [f0 - 1, f0 + 1], btype="band", ftype="butter", fs=fs)
        self.zi = np.zeros(max(len(self.a), len(self.b)) - 1)
        self.prev = 0.0
        self.n_seen = 0

    def push(self, chunk: np.ndarray) -> list[float]:
        """Feed a chunk; return trigger times (seconds since stream start)."""
        chunk = np.asarray(chunk, dtype=float)
        t_last = (self.n_seen + len(chunk) - 1) / self.fs
        self.n_seen += len(chunk)
        if len(chunk) == 0:
            return []
        if self.drop:
            y, self.zi = signal.lfilter(self.b, self.a, chunk[-1:], zi=self.zi)
            times = [t_last]
        else:
            y, self.zi = signal.lfilter(self.b, self.a, chunk, zi=self.zi)
            times = list(t_last - (len(chunk) - 1 - np.arange(len(chunk))) / self.fs)
        out = []
        for yi, ti in zip(y, times):
            if yi > 0 and self.prev < 0:
                out.append(ti + self.delay_s)
            self.prev = yi
        return out
