"""Download and read eyes-closed resting EEG from the PhysioNet EEG Motor Movement/Imagery
Database (Schalk et al., 2004; Goldberger et al., 2000; ODC-By 1.0 licence).

Run 2 of each subject is a 1-minute eyes-closed baseline recorded with 64 electrodes at
160 Hz. The data are downloaded on demand and never redistributed with this repository.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np

MIRRORS = (
    "https://physionet-open.s3.amazonaws.com/eegmmidb/1.0.0",  # PhysioNet open-data mirror on AWS
    "https://physionet.org/files/eegmmidb/1.0.0",
)
DEFAULT_DIR = Path("data/physionet-eegmmidb")


def _download(subject: int, run: int, out_dir: Path, verbose: bool) -> Path:
    name = f"S{subject:03d}R{run:02d}.edf"
    dest = out_dir / name
    if dest.exists():
        return dest
    last_err = None
    for base in MIRRORS:
        url = f"{base}/S{subject:03d}/{name}"
        try:
            tmp = dest.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(dest)
            if verbose:
                print(f"downloaded {name}")
            return dest
        except OSError as err:  # try the next mirror
            last_err = err
    raise RuntimeError(f"could not download {name}: {last_err}")


def fetch(subjects=range(1, 110), run: int = 2, out_dir: Path = DEFAULT_DIR, verbose: bool = True) -> list[Path]:
    """Download run ``run`` for each subject (parallel, cached)."""
    from concurrent.futures import ThreadPoolExecutor

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda s: _download(s, run, out_dir, verbose), subjects))


def read_edf(path: Path) -> dict:
    """Minimal EDF/EDF+ reader (16-bit). Returns {label: (signal_uV, fs)}."""
    raw = Path(path).read_bytes()
    n_records = int(raw[236:244])
    rec_dur = float(raw[244:252])
    ns = int(raw[252:256])
    off = 256

    def field(width):
        nonlocal off
        vals = [raw[off + i * width : off + (i + 1) * width].decode("ascii", "replace").strip() for i in range(ns)]
        off += width * ns
        return vals

    labels = field(16)
    field(80)  # transducer
    field(8)  # physical dimension
    pmin = np.array(field(8), float)
    pmax = np.array(field(8), float)
    dmin = np.array(field(8), float)
    dmax = np.array(field(8), float)
    field(80)  # prefilter
    spr = np.array(field(8), int)
    field(32)
    header_bytes = int(raw[184:192])
    data = np.frombuffer(raw[header_bytes:], dtype="<i2")
    rec_len = int(spr.sum())
    n_records = min(n_records, len(data) // rec_len) if n_records > 0 else len(data) // rec_len
    data = data[: n_records * rec_len].reshape(n_records, rec_len)
    out, start = {}, 0
    for i, lab in enumerate(labels):
        seg = data[:, start : start + spr[i]].reshape(-1).astype(float)
        start += spr[i]
        if lab.startswith("EDF Annotations"):
            continue
        gain = (pmax[i] - pmin[i]) / (dmax[i] - dmin[i])
        out[lab.rstrip(".").strip(".")] = ((seg - dmin[i]) * gain + pmin[i], spr[i] / rec_dur)
    return out


def occipital_channel(path: Path, prefer=("Oz", "O1", "O2")) -> tuple[np.ndarray, float, str]:
    sigs = read_edf(path)
    for name in prefer:
        if name in sigs:
            x, fs = sigs[name]
            return x, fs, name
    raise KeyError(f"no occipital channel in {path}")
