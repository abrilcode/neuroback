# Safety and privacy

## Photosensitive epilepsy

NeuroBack flashes light at the participant's alpha frequency, about 8–13 Hz.
- Flicker at 3–30 Hz is the most common trigger of photosensitive seizures (Epilepsy Society, 2025), and some people are sensitive up to 60 Hz.
- Clinical EEG labs find that eyes-closed photic stimulation at roughly 10–20 Hz is among the most provocative settings. That is exactly NeuroBack's regime.

**Built into the software**
- Stimulation is locked until a participant has answered the photosensitivity screening, with every answer "no", and consent is recorded. See `src/neuroback/safety.py`.
- A permanent on-screen warning.
- **STOP** button and **Esc** shortcut: they cancel every pending flash immediately.
- `max_session_min` in the session config (default 45 min).

**Researcher responsibilities**
- Screen every participant and exclude anyone with a personal or family history of epilepsy or seizures, or flicker-triggered symptoms.
- Use a **diffused** LED at modest brightness, off the central field of view, and avoid saturated red light.
- Stop at the first report of discomfort, visual disturbance, nausea or headache.
- Obtain ethics approval before testing on participants, and follow institutional rules.
- Consider auditory pulses instead of light. That variant is better replicated (Hebron et al., 2024) and avoids photosensitivity risk.

## Not a medical device

NeuroBack is research and teaching software. It makes no diagnostic or therapeutic claims.
- **United States:** making therapeutic claims would turn it into a medical device, Class II for biofeedback (21 CFR 882.5050).
- **Argentina:** software that observes physiological processes is Class II under ANMAT Disposición 64/2025.

## Privacy by design

EEG linked to a person is health data:
- sensitive data under Argentina's Ley 25.326;
- special-category data under GDPR Art. 9;
- "neural data" under the Colorado (2024) and California (2025) privacy laws.

The UNESCO Recommendation on the Ethics of Neurotechnology (2025) asks for opt-in consent and data minimisation.

**What NeuroBack does**
- **Pseudonyms only.** Participants are random IDs such as `P-7F3A1C`. No names are stored anywhere. Keep any ID-to-person key offline, under institutional controls.
- **Minimal data:** age band (not date of birth), screening outcome and consent time.
- **Fixed schema, parameterised SQL.** The 2023 app built table names from patient names, which allowed SQL injection.
- **Erasure:** "Delete participant and data" removes the database rows and session files.
- **Local only:** nothing is uploaded anywhere.

**Recommended additions for real studies:** disk encryption, access control, a data-management plan, and retention limits.
