"""Photosensitivity screening and consent.

NeuroBack flashes light at the participant's alpha frequency (~8-13 Hz). That is inside
the 3-30 Hz range where photosensitive seizures are most commonly triggered (Epilepsy
Society, 2025). Stimulation is locked until screening and consent are recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

SCREENING_QUESTIONS = (
    "Any history of seizures, convulsions or an epilepsy diagnosis",
    "Epilepsy in a first-degree relative (parent, sibling, child)",
    "Discomfort, dizziness or migraine ever triggered by flashing or flickering light (screens, strobes, sunlight through trees)",
    "Current medication or substance known to lower the seizure threshold, or sleep deprivation today",
    "Any neurological, psychiatric or eye condition not yet discussed with the study team",
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
