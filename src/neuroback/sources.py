"""EEG sources: OpenBCI Cyton (via BrainFlow), BrainFlow's synthetic board, a realistic
simulated alpha generator, and playback of recorded arrays.

Every source returns *all* new samples of one EEG channel on each ``read()`` call. The
2023 loop kept only the last sample of each chunk, which silently sub-sampled the signal
whenever the Cyton's USB dongle delivered samples in bursts.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np

from .simulate import alpha_eeg


class EEGSource(ABC):
    fs: float = 250.0
    label: str = "source"

    def start(self) -> None:
        self._t0 = time.perf_counter()

    @abstractmethod
    def read(self) -> np.ndarray:
        """Return the samples that arrived since the last call (microvolts, 1-D)."""

    def stop(self) -> None:
        pass


class SimulatedAlpha(EEGSource):
    """Realistic alpha (AR(2) resonance + 1/f background) streamed in real time.

    With ``realtime=False`` each ``read(n)`` returns exactly ``n`` samples, which makes
    tests and screenshots deterministic.
    """

    def __init__(self, fs: float = 250.0, iaf: float = 10.2, seed: int = 7, realtime: bool = True):
        self.fs = fs
        self.label = f"Simulated alpha · {fs:g} Hz"
        self.realtime = realtime
        self.eyes_closed = True
        self._ec = alpha_eeg(600, fs, iaf=iaf, seed=seed, eyes_closed=True)
        self._eo = alpha_eeg(600, fs, iaf=iaf, seed=seed + 1, eyes_closed=False)
        self._i = 0

    def start(self) -> None:
        super().start()
        self._emitted = 0

    def read(self, n: int | None = None) -> np.ndarray:
        if n is None:
            due = int((time.perf_counter() - self._t0) * self.fs)
            n = max(0, due - self._emitted)
        self._emitted = getattr(self, "_emitted", 0) + n
        src = self._ec if self.eyes_closed else self._eo
        idx = (self._i + np.arange(n)) % len(src)
        self._i += n
        return src[idx]


class ArrayPlayback(EEGSource):
    """Replay a recorded 1-D signal in real time (or instantly with ``realtime=False``)."""

    def __init__(self, x: np.ndarray, fs: float, label: str = "Playback", realtime: bool = True, loop: bool = True):
        self.x = np.asarray(x, dtype=float)
        self.fs = fs
        self.label = f"{label} · {fs:g} Hz"
        self.realtime = realtime
        self.loop = loop
        self._i = 0

    def start(self) -> None:
        super().start()
        self._emitted = 0

    def read(self, n: int | None = None) -> np.ndarray:
        if n is None:
            n = max(0, int((time.perf_counter() - self._t0) * self.fs) - self._emitted)
        self._emitted = getattr(self, "_emitted", 0) + n
        if self.loop:
            idx = (self._i + np.arange(n)) % len(self.x)
        else:
            idx = np.arange(self._i, min(self._i + n, len(self.x)))
        self._i += n
        return self.x[idx]


class BrainFlowSource(EEGSource):
    """OpenBCI Cyton (or BrainFlow's synthetic board) through BrainFlow.

    ``channel`` is 1-based, matching the Cyton's N1P..N8P inputs. Set the FTDI latency
    timer to 1 ms on the host (see docs/hardware.md): with the default buffer, samples
    arrive in large bursts with ~330 ms lag (Knierim et al., 2023), far too late to
    close a loop on a 100 ms alpha cycle.
    """

    def __init__(self, board: str = "cyton", serial_port: str = "", channel: int = 8):
        from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams

        ids = {"cyton": BoardIds.CYTON_BOARD, "synthetic": BoardIds.SYNTHETIC_BOARD}
        self.board_id = ids[board].value
        params = BrainFlowInputParams()
        params.serial_port = serial_port
        self.shim = BoardShim(self.board_id, params)
        self.fs = float(BoardShim.get_sampling_rate(self.board_id))
        self.eeg_row = BoardShim.get_eeg_channels(self.board_id)[channel - 1]
        self.ts_row = BoardShim.get_timestamp_channel(self.board_id)
        self.label = f"{'OpenBCI Cyton' if board == 'cyton' else 'BrainFlow synthetic'} · ch {channel} · {self.fs:g} Hz"
        self.last_timestamp: float | None = None

    def start(self) -> None:
        super().start()
        self.shim.prepare_session()
        self.shim.start_stream(45000)

    def read(self) -> np.ndarray:
        data = self.shim.get_board_data()
        if data.shape[1]:
            self.last_timestamp = float(data[self.ts_row, -1])
        return data[self.eeg_row].astype(float)

    def stop(self) -> None:
        try:
            self.shim.stop_stream()
        finally:
            self.shim.release_session()
