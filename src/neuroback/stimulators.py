"""Stimulus outputs and a precise trigger scheduler.

The 2023 code slept inside a new thread per zero-crossing and, in the final stage, passed
the index of the best delay (0-10) to ``time.sleep`` as *seconds*. Here a single
scheduler thread owns the timing and every delay is in seconds by construction.
"""

from __future__ import annotations

import heapq
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable


class Stimulator(ABC):
    @abstractmethod
    def flash(self) -> None: ...

    def close(self) -> None:
        pass


class SerialTrigger(Stimulator):
    """Arduino running ``firmware/neuroback_trigger``: one byte ``F`` = one LED pulse."""

    def __init__(self, port: str, baud: int = 115200):
        import serial

        self.ser = serial.Serial(port, baud, timeout=0)
        time.sleep(2.0)  # Arduino resets when the port opens

    def flash(self) -> None:
        self.ser.write(b"F")

    def close(self) -> None:
        self.ser.close()


class VirtualStimulator(Stimulator):
    """Records flash times and calls ``on_flash`` (used by the GUI's on-screen LED)."""

    def __init__(self, on_flash: Callable[[], None] | None = None):
        self.on_flash = on_flash
        self.times: list[float] = []

    def flash(self) -> None:
        self.times.append(time.perf_counter())
        if self.on_flash:
            self.on_flash()


class TriggerScheduler:
    """Fire ``stimulator.flash()`` at absolute ``time.perf_counter()`` deadlines.

    Two kinds of deadline:

    * ``tentative(t)``: the engine's current best guess for the next stimulus. Each call
      replaces the previous guess, so estimates are refined as new samples arrive.
    * ``commit(t)``: a stimulus that must fire (queued; never overwritten).

    The thread waits on a condition variable until ~20 ms before the next deadline, then
    polls with 0.5 ms sleeps (so refinements and cancels still apply), then spins for the
    last millisecond. OS timer wake-ups alone can be several ms late on desktop systems;
    this keeps flashes within ~1 ms. ``stop()`` (the GUI's STOP button) cancels
    everything immediately.
    """

    COARSE_S = 0.020
    SPIN_S = 0.001
    DEDUP_S = 0.010

    def __init__(self, stimulator: Stimulator):
        self.stim = stimulator
        self._tentative: float | None = None
        self._committed: list[float] = []
        self._last_fired = -1.0
        self._cv = threading.Condition()
        self._running = True
        self.enabled = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def tentative(self, deadline: float) -> None:
        with self._cv:
            self._tentative = deadline
            self._cv.notify()

    schedule = tentative

    def commit(self, deadline: float) -> None:
        with self._cv:
            if abs(deadline - self._last_fired) > self.DEDUP_S:
                heapq.heappush(self._committed, deadline)
            if self._tentative is not None and abs(self._tentative - deadline) < self.DEDUP_S:
                self._tentative = None
            self._cv.notify()

    def cancel(self) -> None:
        with self._cv:
            self._tentative = None
            self._committed.clear()

    def stop(self) -> None:
        with self._cv:
            self._running = False
            self._tentative = None
            self._committed.clear()
            self._cv.notify()

    def _next(self) -> float | None:
        cands = [d for d in (self._tentative, self._committed[0] if self._committed else None) if d is not None]
        return min(cands) if cands else None

    def _run(self) -> None:
        while True:
            with self._cv:
                while self._running and self._next() is None:
                    self._cv.wait()
                if not self._running:
                    return
                deadline = self._next()
                remaining = deadline - time.perf_counter()
                if remaining > self.COARSE_S:
                    self._cv.wait(timeout=remaining - self.COARSE_S)
                    continue  # re-check: the deadline may have been refined or cancelled
            if remaining > self.SPIN_S:
                time.sleep(min(0.0005, remaining - self.SPIN_S))
                continue
            with self._cv:
                if not self._running or self._next() != deadline:
                    continue
                if self._committed and self._committed[0] == deadline:
                    heapq.heappop(self._committed)
                else:
                    self._tentative = None
                self._last_fired = deadline
            while time.perf_counter() < deadline:
                pass
            if self.enabled:
                self.stim.flash()
