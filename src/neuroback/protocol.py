"""Session protocol: calibration, a randomised phase sweep with controls, and stimulation."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Condition:
    kind: str  # "phase" | "open-loop" | "random-phase"
    target_deg: float | None = None

    @property
    def label(self) -> str:
        if self.kind == "phase":
            return f"{self.target_deg:g}°"
        return {"open-loop": "Open-loop at IAF", "random-phase": "Random phase"}[self.kind]


@dataclass
class SweepConfig:
    """Phase sweep that can actually separate a phase effect from drift and flicker.

    The 2023 sweep tested 11 delays once each, 20 s, in ascending order, so slow drift in
    alpha (which rises with time on task) looked like a phase effect. Here every condition
    is repeated in random order, alpha is also measured in the stimulus-free gap after
    each block (no steady-state visual response there), and two controls with the same
    flash rate are included.
    """

    phases_deg: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)
    include_open_loop: bool = True
    include_random_phase: bool = True
    repeats: int = 4
    on_s: float = 20.0
    off_s: float = 10.0
    seed: int | None = None

    def conditions(self) -> list[Condition]:
        conds = [Condition("phase", p) for p in self.phases_deg]
        if self.include_open_loop:
            conds.append(Condition("open-loop"))
        if self.include_random_phase:
            conds.append(Condition("random-phase"))
        return conds

    def schedule(self) -> list[Condition]:
        """Blocks in randomised order, each condition once per repeat (block-randomised)."""
        rng = random.Random(self.seed)
        order: list[Condition] = []
        for _ in range(self.repeats):
            rep = self.conditions()
            rng.shuffle(rep)
            order.extend(rep)
        return order

    @property
    def duration_s(self) -> float:
        return len(self.conditions()) * self.repeats * (self.on_s + self.off_s)


@dataclass
class CalibrationConfig:
    eyes_open_s: float = 60.0
    eyes_closed_s: float = 60.0


@dataclass
class SessionConfig:
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    sweep: SweepConfig = field(default_factory=SweepConfig)
    estimator: str = "ecHT"
    output_latency_ms: float = 0.0  # measure with a photodiode, see docs/hardware.md
    stimulation_s: float = 120.0
    max_session_min: float = 45.0

    def to_dict(self) -> dict:
        return asdict(self)
