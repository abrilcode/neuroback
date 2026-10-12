import numpy as np
import pytest

from neuroback import cli
from neuroback.bench.physionet import read_edf
from neuroback.dsp import band_power
from neuroback.sources import ArrayPlayback, SimulatedAlpha


def test_cli_demo_reports_locking(capsys):
    assert cli.main(["demo", "--seconds", "30"]) == 0
    out = capsys.readouterr().out
    plv = float(out.split("phase-locking value ")[1].split()[0])
    assert plv > 0.6


def test_simulated_source_blocks_alpha_with_eyes_open():
    src = SimulatedAlpha(realtime=False)
    src.start()
    ec = src.read(2500)
    src.eyes_closed = False
    eo = src.read(2500)
    assert len(ec) == 2500
    assert band_power(ec, 250, (8, 12)) > 3 * band_power(eo, 250, (8, 12))


def test_playback_loops():
    src = ArrayPlayback(np.arange(10.0), 250.0, realtime=False)
    src.start()
    assert list(src.read(12)) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 1]


def _write_edf(path, signals, fs, rec_s=1):
    ns, n = len(signals), len(next(iter(signals.values())))
    spr = int(fs * rec_s)
    nrec = n // spr

    def f(v, w):
        return str(v).ljust(w)[:w].encode()

    hdr = f("0", 8) + f("X", 80) + f("X", 80) + f("01.01.26", 8) + f("00.00.00", 8)
    hdr += f(256 + 256 * ns, 8) + f("", 44) + f(nrec, 8) + f(rec_s, 8) + f(ns, 4)
    labels = list(signals)
    for width, vals in ((16, [l + "." for l in labels]), (80, [""] * ns), (8, ["uV"] * ns), (8, ["-3276.8"] * ns),
                        (8, ["3276.7"] * ns), (8, ["-32768"] * ns), (8, ["32767"] * ns), (80, [""] * ns),
                        (8, [spr] * ns), (32, [""] * ns)):
        hdr += b"".join(f(v, width) for v in vals)
    data = b""
    for r in range(nrec):
        for lab in labels:
            seg = np.round(np.asarray(signals[lab][r * spr:(r + 1) * spr]) * 10).astype("<i2")
            data += seg.tobytes()
    path.write_bytes(hdr + data)


def test_edf_reader_roundtrip(tmp_path):
    t = np.arange(0, 4, 1 / 160)
    oz = 20 * np.sin(2 * np.pi * 10 * t)
    p = tmp_path / "x.edf"
    _write_edf(p, {"Oz": oz, "Cz": -oz}, 160)
    sigs = read_edf(p)
    x, fs = sigs["Oz"]
    assert fs == 160 and np.allclose(x, oz, atol=0.11)


def test_gui_smoke(tmp_path):
    pytest.importorskip("PyQt6")
    pytest.importorskip("pyqtgraph")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from neuroback.gui.app import render_screenshots

    paths = render_screenshots(tmp_path)
    assert len(paths) == 5 and all(p.stat().st_size > 10_000 for p in paths)
