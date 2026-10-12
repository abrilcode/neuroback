# Session protocol

Defaults live in `src/neuroback/protocol.py`.

## 1. Calibration (2 min)

1. **Eyes open, 60 s.** Fixate a point.
2. **Eyes closed, 60 s.** Relaxed, awake.
3. **Individual alpha frequency (IAF).** NeuroBack computes the peak after removing the 1/f background from the eyes-closed spectrum. It reports:
   - the IAF (Hz);
   - the peak height above 1/f (dB);
   - eyes-closed / eyes-open alpha power (reactivity).

   Low reactivity (below ×2) or a weak peak (below ~3 dB) usually means poor contact or the wrong electrode. Fix that before going on.
4. **Amplitude gate.** The 25th percentile of the eyes-closed alpha envelope becomes the gate: cycles weaker than this get no flash.

## 2. Phase sweep (default 12 min)

| Condition | What happens |
|---|---|
| 0°, 90°, 180°, 270° | Closed loop, one flash per alpha cycle at that phase |
| Open-loop at IAF | Flashes at the IAF, ignoring phase (same rate, no phase relation) |
| Random phase | Same mean rate, random phase on each cycle |

- **Timing:** each block is 20 s of stimulation followed by 10 s with no stimulus.
- **Order:** every condition appears once per repeat, in random order; 4 repeats by default.
- **Outcome:** alpha power (IAF ± 2 Hz) in the stimulus-free gap after each block, where there is no steady-state visual response. On-block power is stored too, but it is contaminated by that response.
- **Test:** a permutation test (5,000 shuffles of phase labels) on a cosine fit across the four target phases gives a p-value and a preferred phase.
- **Controls:** these show whether any change is specific to phase. If open-loop flicker changes alpha as much as the best phase, the effect is flicker, not phase.

**Good practice for a real study**
- Preregister the primary outcome.
- Choose the preferred phase on one half of the blocks and confirm it on the other half.
- Report using the CRED-nf checklist (Ros et al., 2020).

## 3. Stimulation

- Choose a target phase and stimulate.
- The live panel shows where flashes actually landed, measured one second later with the non-causal phase:
  - phase-locking value;
  - mean error;
  - flash rate.
- Every flash and event is saved with the raw EEG (`events.json` + `eeg.npz`).
