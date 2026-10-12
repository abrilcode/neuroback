# Contributing

Issues and pull requests are welcome, especially:
- hardware latency measurements;
- new phase estimators (benchmark them with `neuroback benchmark`);
- an auditory stimulus output;
- LSL / XDF support.

```bash
pip install -e ".[all]"
pytest
python scripts/make_figures.py   # after `neuroback benchmark`
```

Please do not add therapeutic or diagnostic claims to the code or docs. NeuroBack is research and teaching software.
