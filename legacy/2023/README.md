# NeuroBack v1 (2023): original code

This is the code handed in on 29 November 2023 for *Instrumentación Biomédica II* at ITBA. It is preserved **unchanged** for reference and is not maintained.

Known issues are documented, and reproduced from the original files, in [docs/postmortem-2023.md](../../docs/postmortem-2023.md). In short:
- dropped samples in the real-time loop;
- the delay index slept as seconds;
- duplicated recordings and misaligned analysis windows;
- a 1.34 Hz alpha-frequency grid;
- patient names used as SQL table names.

Use the maintained package in `src/neuroback/` instead.
