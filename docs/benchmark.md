# Phase-accuracy benchmark

**Question.** When NeuroBack aims a flash at a given alpha phase, where does it actually land?

**Short answer.** On real eyes-closed EEG from 109 people:
- **ecHT:** median phase-locking value 0.74 and circular spread ±44°, aimed at the peak.
- **2023 rule, input bug fixed:** 0.42.
- **2023 code as shipped:** 0.08.

ecHT was better than the 2023 rule in every one of the 109 people (Wilcoxon signed-rank p ≈ 10⁻¹⁹).

Reproduce everything:

```bash
neuroback benchmark          # downloads ~140 MB from PhysioNet's AWS mirror, ~2 minutes
python scripts/make_figures.py
```

## Data

- **Dataset:** PhysioNet EEG Motor Movement/Imagery Database v1.0.0 (Schalk et al., 2004; Goldberger et al., 2000), licence ODC-By 1.0. The data are downloaded on demand and never redistributed here.
- **Recordings:** run 2 for all 109 subjects, a 1-minute eyes-closed resting baseline. 64 electrodes were recorded at 160 Hz.
- **Channel:** Oz, the occipital site the 2023 project used. Resampled 160 → 250 Hz (polyphase) to match the OpenBCI Cyton.

## Procedure, per subject

1. **Individual alpha frequency (IAF).**
   - Welch PSD with 4 s Hann segments, zero-padded to 0.05 Hz.
   - The aperiodic (1/f) trend is removed with a log–log line fitted over 2–35 Hz, excluding 7–14 Hz.
   - The IAF is the largest residual peak in 7–14 Hz, clipped to 7.5–13 Hz.
   - Median IAF was 10.2 Hz.
2. **Ground truth.**
   - Zero-phase Butterworth band-pass at IAF ± 2 Hz, then a Hilbert transform over the whole recording.
   - This needs future samples, so it is only possible offline.
   - It is itself noisy at low SNR (Zrenner et al., 2020). Treat absolute numbers as conservative.
3. **Live stream.**
   - The recording is fed to each method in 4-sample (16 ms) chunks, in order.
   - Each method sees only the past and outputs flash times. Target: the alpha peak (0°).
4. **Scoring.**
   - Ground-truth phase is read at every flash time.
   - Phase-locking value (PLV) is the mean resultant length of (true phase − target): 1 means every flash lands at the same phase, 0 means uniformly random.
   - Also reported: circular SD (√(−2 ln PLV)), mean error (bias), and the share of alpha cycles that received a flash.
5. **Jitter.** Every flash time is perturbed with Gaussian noise (SD 3 ms) and rescored. For comparison, the Cyton with the 1 ms FTDI fix measured 2.1 ms jitter at 250 Hz (Knierim et al., 2023).

## Methods compared

| Method | What it is | Settings |
|---|---|---|
| **2023 code, as shipped** | The original rule: causal `iirfilter(2, [PAF−1, PAF+1])`, flash on each rising zero-crossing. Only the last sample of each chunk is fed to the filter, as in the 2023 loop. | Oracle delay (see below) |
| **2023 rule, input bug fixed** | Same rule, but every sample goes into the filter | Oracle delay |
| **AR forecast** | Zero-phase FIR band-pass (IAF ± 2 Hz, 33 taps) on a 0.5 s window. The distorted last 16 samples are replaced by an AR(8) Yule–Walker forecast, then a Hilbert transform is taken over a 256 ms span centred on "now" (phastimate-style; Zrenner et al., 2018, 2020). | Projected to target at the IAF |
| **ecHT** | Endpoint-corrected Hilbert transform (Schreglmann et al., 2021): FFT of a 0.5 s window, analytic signal, multiplied by the response of a causal 2nd-order band-pass (IAF ± 2 Hz), phase taken at the last sample | Projected to target at the IAF |

- **Oracle delay.** The 2023 rule can only fire at a fixed delay after a zero-crossing. Each person gets the single delay that best centres their flashes on the target. A perfect calibration sweep would have found this; the 2023 sweep could not (see [postmortem-2023.md](postmortem-2023.md)). This is generous to the 2023 rule.
- **No tuning on real data.** Window lengths, bandwidths and the AR order were chosen on synthetic alpha only (`scripts/_tune_synthetic.py`), never on the PhysioNet data.

## Results (n = 109)

| Method | PLV median (IQR) | Spread (circular SD) | Bias | Cycles stimulated | PLV with 3 ms jitter |
|---|---|---|---|---|---|
| 2023 code, as shipped | 0.08 (0.04–0.11) | ±129° | 11.4° | 25% | 0.07 |
| 2023 rule, input bug fixed | 0.42 (0.31–0.53) | ±75° | 1.0° | 100% | 0.41 |
| AR forecast | 0.64 (0.52–0.78) | ±54° | 4.0° | 83% | 0.63 |
| **ecHT** | **0.74 (0.67–0.83)** | **±44°** | **4.2°** | **82%** | **0.73** |

**ecHT PLV by alpha amplitude at the moment of the flash** (within-person quartiles): 0.44 → 0.74 → 0.85 → 0.94. NeuroBack's amplitude gate (25th percentile of the calibration envelope) skips the weakest cycles during live use.

**Other target phases.** Median mean error for ecHT:

| Target | Mean error |
|---|---|
| 0° | +2.4° |
| 90° | −0.1° |
| 180° | +3.0° |
| 270° | −0.3° |

**Subjects with a clear alpha peak** (≥ 6 dB above 1/f, n = 92): ecHT 0.77, 2023 rule with input fixed 0.45, AR 0.66, as shipped 0.08.

![Where flashes land](figures/benchmark-polar.png)
![Per-person results](figures/benchmark-subjects.png)

## How this compares with published systems

| System | Accuracy | Notes |
|---|---|---|
| ecHT, offline, Schreglmann et al. (2021) | 9 ± 2° endpoint error | Tremor recordings; ~0.5 s windows |
| ecHT, live auditory stimulation of alpha, Hebron et al. (2024) | Resultant ~0.84 | Lab-grade amplifier |
| ecHT in the Elemind headband, Harlow et al. (2024) | PLV 0.92 vs 0.68 for a plain Hilbert transform | — |
| Autoregressive forecasting, Zrenner et al. (2020) | 20–50° error spread in the highest-amplitude quartile, 70–100° in the lowest | Even the non-causal "truth" scatters 6.5–17.5° |

NeuroBack's numbers come from scalp EEG sampled at 160 Hz and upsampled, on the same ground-truth definition. They are in line with these systems.

## Limitations

- **Software only.** No Cyton or LED was in the loop. Real systems add output latency and jitter (radio link, USB, serial, LED rise time). Measure them with the photodiode loop-back in [hardware.md](hardware.md) and pass `--latency-ms`.
- **One minute per person**, eyes closed: the easiest condition for alpha tracking. Eyes open, movement and drowsiness will lower all numbers.
- **The ground truth is itself an estimate.** It shares the IAF ± 2 Hz band with the estimators, which favours band-limited methods slightly.
- **This measures timing accuracy only.** Whether stimulating at a given phase changes alpha or behaviour is a separate, experimental question (see [science.md](science.md)).
