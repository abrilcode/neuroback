# Changelog

## 2.0.0 (2026-10-12): rebuild

- **Phase estimation.** Endpoint-corrected Hilbert transform (default) and AR forecasting replace the zero-crossing + fixed-delay rule. The 2023 rule is kept for comparison.
- **Closed-loop engine.**
  - Processes every sample.
  - Refines each stimulus time per chunk.
  - Compensates output latency.
  - Gates on alpha amplitude.
  - One stimulus per cycle.
- **Scheduler.** A single thread with sub-millisecond deadlines. Fixes the 2023 bug where the delay index was slept as seconds.
- **Protocol.** Randomised, repeated phase sweep with open-loop and random-phase controls, post-block alpha, permutation test.
- **Individual alpha frequency.** 1/f-corrected peak at ~0.05 Hz resolution (was a 1.34 Hz grid), plus a reactivity check.
- **Benchmark.** Phase accuracy on real EEG from 109 people (PhysioNet EEGMMIDB), reproducible with `neuroback benchmark`.
- **Desktop app.** New PyQt6 step flow (Participant → Calibrate → Phase sweep → Stimulate → Results) with a phase dial, live accuracy and an emergency stop.
- **Safety and privacy.**
  - Photosensitivity screening and consent gate.
  - Pseudonymous storage with parameterised SQL and erasure.
- **Hardware.** Arduino firmware with non-blocking pulses and a TTL marker output.
- **Docs.** Benchmark method, science review with citations, hardware and latency calibration, protocol, safety, and a post-mortem of v1.

## 1.0 (2023-11-23): ITBA course project

- OpenBCI Cyton + BrainFlow + PyQt6 app with SQLite patient records.
- Causal band-pass at the peak alpha frequency, LED triggered on rising zero-crossings via an Arduino Mega.
- See `docs/postmortem-2023.md` for known issues.
