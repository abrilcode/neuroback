"""Photosensitivity screening and consent.

NeuroBack flashes light at the participant's alpha frequency (~8-13 Hz). That is inside
the 3-30 Hz range where photosensitive seizures are most commonly triggered (Epilepsy
Society, 2025). Stimulation is locked until screening and consent are recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

SCREENING_QUESTIONS = (
    "Have you ever had a seizure, convulsion or epilepsy diagnosis?",
    "Has a close relative (parent, sibling, child) been diagnosed with epilepsy?",
    "Have flashing or flickering lights (screens, strobes, sunlight through trees) ever made you feel unwell, dizzy or caused migraine?",
    "Are you taking any medication or substance known to lower the seizure threshold, or are you sleep-deprived today?",
    "Do you have any neurological, psychiatric or eye condition you have not discussed with the study team?",
)

WARNING = (
    "This device flashes light at 8-13 Hz. Flicker in this range can trigger seizures in "
    "people with photosensitive epilepsy, sometimes without any prior history. Stop "
    "immediately (STOP button or Esc) if the participant reports discomfort, visual "
    "disturbance, nausea or headache. Research and teaching use only. Not a medical device."
)


@dataclass(frozen=True)
class Screening:
    answers: tuple[bool, ...]  # True = "yes"
    consent: bool

    @property
    def passed(self) -> bool:
        return self.consent and len(self.answers) == len(SCREENING_QUESTIONS) and not any(self.answers)
