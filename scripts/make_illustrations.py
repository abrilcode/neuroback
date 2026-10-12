"""Vector illustrations: the README hero and the hardware-setup diagram.

    python scripts/make_illustrations.py

Builds SVG in code and renders it to PNG with headless Chrome, so every line stays sharp
and editable. The EEG trace and flash markers in the hero are real: PhysioNet subject
S004 (channel Oz) run through NeuroBack's closed loop.
"""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from neuroback.bench.physionet import fetch, occipital_channel  # noqa: E402
from neuroback.closedloop import ClosedLoop, run_offline  # noqa: E402
from neuroback.dsp import individual_alpha_frequency, offline_phase, resample  # noqa: E402
from neuroback.phase import EcHT  # noqa: E402

ASSETS = ROOT / "assets"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

BG, PANEL, PANEL2, BORDER = "#0A1820", "#10232C", "#153140", "#21404D"
TEXT, MUTED, MINT, FLASH, RED, BLUE = "#E7F1F3", "#8BA6AF", "#6AFFA4", "#FFD166", "#FF5C61", "#5AB4FF"
FONT = "'Avenir Next', 'Helvetica Neue', Helvetica, Arial, sans-serif"

# ----------------------------------------------------------------------------- head + brain
# Local coordinates: a head in profile facing right, about 300 x 380.
HEAD = ("M95,380 C90,330 60,300 45,260 C20,200 20,120 60,70 C100,20 190,10 235,55 C262,85 270,120 268,150 "
        "C268,165 272,172 276,180 C285,200 300,225 298,235 C296,242 285,245 280,246 C284,252 286,262 281,268 "
        "C279,271 283,276 283,282 C282,292 276,300 272,305 C268,318 262,328 245,332 C225,335 205,335 195,345 "
        "C190,355 192,370 195,380 Z")
BRAIN = ("M60,175 C35,150 35,100 65,70 C100,35 180,30 225,62 C250,82 258,120 250,150 C246,170 230,180 215,182 "
         "C205,190 210,205 195,212 C170,222 130,215 110,200 C95,195 75,190 60,175 Z")
EYE = (247.0, 170.0)
OZ = (21.0, 160.0)
EAR = (150.0, 214.0)
V1 = (52.0, 126.0)
PATHWAY = "M245,172 C225,185 210,192 195,191 C170,188 155,170 140,162 C112,150 82,140 54,127"


def gyri(seed: int = 4, n: int = 46) -> str:
    """Procedural sulci: smooth random 'worms' inside the brain outline (clipped)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        x, y = rng.uniform(45, 250), rng.uniform(40, 210)
        ang = rng.uniform(0, 2 * math.pi)
        pts = [(x, y)]
        for _ in range(rng.integers(4, 9)):
            ang += rng.normal(0, 0.9)
            step = rng.uniform(8, 15)
            x, y = x + step * math.cos(ang), y + step * math.sin(ang)
            pts.append((x, y))
        d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f} " + " ".join(
            f"Q{pts[i][0]:.1f},{pts[i][1]:.1f} {(pts[i][0] + pts[i + 1][0]) / 2:.1f},{(pts[i][1] + pts[i + 1][1]) / 2:.1f}"
            for i in range(1, len(pts) - 1))
        op = rng.choice([0.16, 0.24, 0.32])
        out.append(f'<path d="{d}" fill="none" stroke="{MINT}" stroke-opacity="{op}" stroke-width="1.6" stroke-linecap="round"/>')
    return "\n".join(out)


def head_group(uid: str, tx: float, ty: float, s: float, mirror: bool = False, labels: bool = True) -> str:
    sx = -s if mirror else s
    cb = ("M70,197 C60,210 72,234 100,236 C126,238 140,226 136,212 C128,200 100,196 70,197 Z")
    return f"""
<g transform="translate({tx},{ty}) scale({sx},{s})">
  <defs>
    <clipPath id="brainclip-{uid}"><path d="{BRAIN}"/></clipPath>
    <radialGradient id="occ-{uid}" cx="{V1[0]}" cy="{V1[1]}" r="70" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{MINT}" stop-opacity="0.75"/>
      <stop offset="0.55" stop-color="{MINT}" stop-opacity="0.18"/>
      <stop offset="1" stop-color="{MINT}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="skin-{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#173544"/><stop offset="1" stop-color="#1D4252"/>
    </linearGradient>
  </defs>
  <path d="{HEAD}" fill="url(#skin-{uid})" stroke="#3E6574" stroke-width="2"/>
  <path d="{BRAIN}" fill="#0E2731" stroke="{MINT}" stroke-opacity="0.55" stroke-width="1.6"/>
  <g clip-path="url(#brainclip-{uid})">
    <rect x="0" y="0" width="300" height="260" fill="url(#occ-{uid})"/>
    {gyri()}
    <path d="M205,180 C182,152 150,146 118,140" fill="none" stroke="{MINT}" stroke-opacity="0.5" stroke-width="2"/>
    <path d="M160,38 C150,80 156,110 140,140" fill="none" stroke="{MINT}" stroke-opacity="0.45" stroke-width="2"/>
  </g>
  <path d="{cb}" fill="#0E2731" stroke="{MINT}" stroke-opacity="0.4" stroke-width="1.4"/>
  <path d="M82,212 C95,206 115,206 130,214 M78,222 C95,216 118,218 132,224" fill="none" stroke="{MINT}" stroke-opacity="0.3" stroke-width="1.2"/>
  <path d="M128,206 C132,240 134,270 140,300" fill="none" stroke="{MINT}" stroke-opacity="0.35" stroke-width="7" stroke-linecap="round"/>
  <path d="{PATHWAY}" fill="none" stroke="{FLASH}" stroke-width="2.6" stroke-dasharray="6 5" filter="url(#glow)"/>
  <circle cx="{V1[0]}" cy="{V1[1]}" r="6" fill="{MINT}" filter="url(#glow)"/>
  <circle cx="140" cy="162" r="4" fill="{FLASH}"/>
  <path d="M236,166 C242,160 254,160 260,168 C254,176 242,176 236,170 Z" fill="#0A1820" stroke="#9CC3CF" stroke-width="1.4"/>
  <circle cx="249" cy="168" r="3.4" fill="{FLASH}"/>
  <path d="M150,180 C138,182 136,200 140,212 C143,222 152,226 156,218 C160,208 156,198 160,190 C162,184 158,180 150,180 Z"
        fill="#1A3B49" stroke="#3E6574" stroke-width="1.4"/>
  <path d="M8,168 C8,160 14,152 22,150" fill="none" stroke="{MINT}" stroke-width="0"/>
  <circle cx="{OZ[0]}" cy="{OZ[1]}" r="8" fill="{BG}" stroke="{MINT}" stroke-width="3"/>
  <circle cx="{OZ[0]}" cy="{OZ[1]}" r="3" fill="{MINT}"/>
  <rect x="{EAR[0] - 6}" y="{EAR[1] - 4}" width="12" height="9" rx="2" fill="#C9D6DA" stroke="#7D97A0"/>
</g>"""


def local_to_global(p, tx, ty, s, mirror=False):
    return (tx - s * p[0], ty + s * p[1]) if mirror else (tx + s * p[0], ty + s * p[1])


# ----------------------------------------------------------------------------- shared defs
def defs() -> str:
    return f"""
<defs>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="3.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="bigglow" x="-100%" y="-100%" width="300%" height="300%">
    <feGaussianBlur stdDeviation="10" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <radialGradient id="bgglow" cx="0.78" cy="0.35" r="0.6">
    <stop offset="0" stop-color="#12343F"/><stop offset="1" stop-color="{BG}"/>
  </radialGradient>
  <linearGradient id="beam" x1="1" y1="0" x2="0" y2="0">
    <stop offset="0" stop-color="{FLASH}" stop-opacity="0.75"/><stop offset="1" stop-color="{FLASH}" stop-opacity="0.04"/>
  </linearGradient>
  <linearGradient id="beamR" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{FLASH}" stop-opacity="0.75"/><stop offset="1" stop-color="{FLASH}" stop-opacity="0.04"/>
  </linearGradient>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/>
  </marker>
  <marker id="arrowY" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="{FLASH}"/>
  </marker>
</defs>"""


def led(x, y, facing="left", s=1.0) -> str:
    """LED module with diffuser. (x, y) = centre of the emitting face."""
    d = -1 if facing == "left" else 1
    hx = x if facing == "left" else x - 56 * s
    return f"""
<g>
  <rect x="{hx + (6 if facing == 'left' else 0) * s}" y="{y - 22 * s}" width="{50 * s}" height="{44 * s}" rx="{8 * s}" fill="#22323A" stroke="#4A6670" stroke-width="1.5"/>
  <rect x="{x - (4 if facing == 'left' else -1) * s}" y="{y - 19 * s}" width="{4 * s}" height="{38 * s}" rx="{2 * s}" fill="#FFFFFF" fill-opacity="0.55"/>
  <circle cx="{x + d * 2 * s}" cy="{y}" r="{11 * s}" fill="{FLASH}" filter="url(#bigglow)"/>
  <circle cx="{x + d * 2 * s}" cy="{y}" r="{6 * s}" fill="#FFF6D6"/>
</g>"""


def eeg_paths(x, fs, alpha, trig, t0, dur, x0, x1, yc, amp, raw_amp):
    """SVG paths for a window of real EEG: raw, alpha band, flash points."""
    tx = np.arange(len(x)) / fs
    m = (tx >= t0) & (tx < t0 + dur)
    k = amp / np.max(np.abs(alpha[m]))
    X = x0 + (tx[m] - t0) / dur * (x1 - x0)
    raw = np.clip(yc - x[m] * k * raw_amp, yc - amp * 1.6, yc + amp * 1.6)
    al = yc - alpha[m] * k
    p_raw = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(X, raw))
    p_al = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(X, al))
    ft = trig[(trig >= t0) & (trig < t0 + dur)]
    fx = x0 + (ft - t0) / dur * (x1 - x0)
    fy = yc - np.interp(ft, tx, alpha) * k
    return p_raw, p_al, list(zip(fx, fy))


def real_eeg():
    path = fetch([4], verbose=False)[0]
    x160, fs_in, _ = occipital_channel(path)
    x = resample(x160, fs_in, 250.0)
    fs = 250.0
    iaf = individual_alpha_frequency(x, fs).freq
    _, _, alpha = offline_phase(x, fs, iaf)
    trig = run_offline(x, fs, ClosedLoop(fs, EcHT(fs, iaf), f0=iaf, target_deg=0), chunk=4)
    return x, fs, alpha, trig


def render(svg: str, w: int, h: int, out: Path, scale: float = 2.0):
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:{BG};}} svg{{display:block}}</style></head><body>{svg}</body></html>"""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "page.html"
        f.write_text(html)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}",
                        f"--force-device-scale-factor={scale}", f"--screenshot={out}", f.as_uri()],
                       check=True, capture_output=True)


def T(x, y, s, size=14, color=TEXT, weight=400, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{color}" font-weight="{weight}" '
            f'text-anchor="{anchor}" {extra}>{s}</text>')


# ----------------------------------------------------------------------------- hero
def hero(x, fs, alpha, trig):
    W, H = 1280, 640
    tx, ty, s = 1192, 36, 0.96  # head faces left, right edge at tx
    eye = local_to_global(EYE, tx, ty, s, True)
    oz = local_to_global(OZ, tx, ty, s, True)
    v1 = local_to_global(V1, tx, ty, s, True)
    ledx, ledy = 812, eye[1] - 2
    p_raw, p_al, flashes = eeg_paths(x, fs, alpha, trig, t0=20.0, dur=3.05, x0=-10, x1=1215, yc=505, amp=46, raw_amp=0.55)
    end_y = float(p_al.split(" L")[-1].split(",")[1])
    flash_svg = "".join(
        f'<line x1="{a:.1f}" y1="{b:.1f}" x2="{a:.1f}" y2="{b - 34:.1f}" stroke="{FLASH}" stroke-opacity="0.28" stroke-width="1.6"/>'
        f'<circle cx="{a:.1f}" cy="{b:.1f}" r="12" fill="{FLASH}" fill-opacity="0.12"/>'
        f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4.6" fill="{FLASH}" filter="url(#glow)"/>' for a, b in flashes)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
{defs()}
<rect width="{W}" height="{H}" fill="url(#bgglow)"/>
<path d="{p_raw}" fill="none" stroke="{MUTED}" stroke-opacity="0.22" stroke-width="1"/>
<path d="{p_al}" fill="none" stroke="{MINT}" stroke-opacity="0.08" stroke-width="12" stroke-linecap="round"/>
<path d="{p_al}" fill="none" stroke="{MINT}" stroke-opacity="0.16" stroke-width="6" stroke-linecap="round"/>
<path d="{p_al}" fill="none" stroke="{MINT}" stroke-width="2.4" stroke-linecap="round"/>
{flash_svg}
<path d="M{oz[0]:.1f},{oz[1]:.1f} C{oz[0] + 40:.1f},{oz[1] + 60:.1f} {oz[0] + 50:.1f},{end_y - 60:.1f} 1215,{end_y:.1f}"
      fill="none" stroke="{MINT}" stroke-width="2" stroke-dasharray="2 5" stroke-linecap="round"/>
<polygon points="{ledx + 10},{ledy - 9} {ledx + 10},{ledy + 9} {eye[0] - 2:.1f},{eye[1] + 16:.1f} {eye[0] - 2:.1f},{eye[1] - 16:.1f}" fill="url(#beamR)"/>
{led(ledx, ledy, facing="right", s=1.0)}
{head_group("hero", tx, ty, s, mirror=True)}
{T(62, 118, "NeuroBack", 84, TEXT, 700)}
{T(65, 172, "Closed-loop light stimulation,", 27, TEXT, 400)}
{T(65, 206, "locked to your alpha rhythm", 27, TEXT, 400)}
{T(66, 250, "OpenBCI Cyton  ·  ecHT phase tracking  ·  109-person EEG benchmark  ·  PyQt6 app", 14.5, MUTED)}
{T(ledx - 6, ledy + 44, "LED flash", 13, FLASH, 600, "middle")}
{T(ledx - 6, ledy + 61, "at the alpha peak", 12, MUTED, 400, "middle")}
{T(v1[0] - 6, v1[1] - 22, "visual cortex (V1)", 12.5, MINT, 600, "end")}
{T(oz[0] + 14, oz[1] + 50, "Oz electrode", 12, MUTED, 400, "start")}
{T(eye[0] + 20, eye[1] + 58, "retina → V1", 12, FLASH, 400, "start")}
{T(1240, 618, "Real EEG · PhysioNet S004 · Oz  ·  yellow = flashes scheduled causally by ecHT at the alpha peak", 11.5, MUTED, 400, "end")}
</svg>"""
    render(svg, W, H, ASSETS / "hero.png", scale=2.0)
    render(svg, W, H, ASSETS / "social-preview.png", scale=1.0)


# ----------------------------------------------------------------------------- hardware setup
def cyton(cx, cy, r=86):
    pts = " ".join(f"{cx + r * math.cos(math.radians(22.5 + 45 * k)):.1f},{cy + r * math.sin(math.radians(22.5 + 45 * k)):.1f}"
                   for k in range(8))
    pins = "".join(f'<circle cx="{cx - 52 + i * 11.5:.1f}" cy="{cy - 62}" r="2.6" fill="#D8B45A"/>' for i in range(10))
    return f"""
<g>
  <polygon points="{pts}" fill="#E3ECEE" stroke="#9FB6BD" stroke-width="2"/>
  <rect x="{cx - 60}" y="{cy - 70}" width="120" height="16" rx="3" fill="#1B2A30"/>{pins}
  <rect x="{cx - 26}" y="{cy - 22}" width="46" height="46" rx="4" fill="#1B2A30"/>
  <rect x="{cx - 19}" y="{cy - 15}" width="32" height="32" rx="3" fill="#24363D"/>
  <rect x="{cx + 32}" y="{cy - 6}" width="26" height="30" rx="3" fill="#1B2A30"/>
  <rect x="{cx - 56}" y="{cy + 34}" width="22" height="12" rx="2" fill="#1B2A30"/>
  <circle cx="{cx - 50}" cy="{cy}" r="9" fill="none" stroke="#9FB6BD" stroke-width="1.5"/>
  <circle cx="{cx + 50}" cy="{cy + 46}" r="5" fill="none" stroke="#9FB6BD" stroke-width="1.5"/>
  {T(cx, cy + 66, "OpenBCI", 11, "#3A5560", 700, "middle")}
</g>"""


def arduino(x, y, w=176, h=108):
    hdr = "".join(f'<circle cx="{x + 34 + i * 10.5:.1f}" cy="{y + 9}" r="2" fill="#D8B45A"/>' for i in range(13))
    hdr2 = "".join(f'<circle cx="{x + 52 + i * 10.5:.1f}" cy="{y + h - 9}" r="2" fill="#D8B45A"/>' for i in range(10))
    return f"""
<g>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="#1F6FA3" stroke="#5FA6D3" stroke-width="1.5"/>
  <rect x="{x + 28}" y="{y + 3}" width="142" height="12" rx="2" fill="#0F2F45"/>{hdr}
  <rect x="{x + 46}" y="{y + h - 15}" width="110" height="12" rx="2" fill="#0F2F45"/>{hdr2}
  <rect x="{x + 70}" y="{y + 40}" width="50" height="30" rx="3" fill="#0F2F45"/>
  <rect x="{x + w - 6}" y="{y + 34}" width="24" height="28" rx="3" fill="#B9C4C9" stroke="#7D8C92"/>
  <rect x="{x - 4}" y="{y + 66}" width="18" height="22" rx="2" fill="#1B1F22"/>
  {T(x + 95, y + 92, "ARDUINO", 11, "#D6ECF8", 700, "middle", 'letter-spacing="2"')}
</g>"""


def laptop(x, y, w, h, x_eeg, fs, alpha, trig, overhang=34):
    p_raw, p_al, flashes = eeg_paths(x_eeg, fs, alpha, trig, t0=31.0, dur=1.6, x0=x + 22, x1=x + 240, yc=y + 118, amp=34, raw_amp=0.6)
    dots = "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.4" fill="{FLASH}"/>' for a, b in flashes)
    dc = (x + 318, y + 118)
    hits = "".join(
        f'<circle cx="{dc[0] + 44 * math.sin(math.radians(a)):.1f}" cy="{dc[1] - 44 * math.cos(math.radians(a)):.1f}" r="2.6" fill="{FLASH}" fill-opacity="0.85"/>'
        for a in np.random.default_rng(2).normal(4, 22, 24))
    return f"""
<g>
  <rect x="{x - 8}" y="{y - 8}" width="{w + 16}" height="{h + 16}" rx="12" fill="#1A2830" stroke="#4A6670" stroke-width="2"/>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{BG}"/>
  <rect x="{x}" y="{y}" width="{w}" height="30" fill="{PANEL}"/>
  {T(x + 14, y + 20, "NeuroBack", 13, TEXT, 700)}
  <rect x="{x + 96}" y="{y + 8}" width="92" height="15" rx="7" fill="{PANEL2}" stroke="{BORDER}"/>
  {T(x + 142, y + 19, "Cyton · 250 Hz", 9, MUTED, 400, "middle")}
  <rect x="{x + w - 58}" y="{y + 7}" width="46" height="17" rx="5" fill="{RED}"/>
  {T(x + w - 35, y + 19, "STOP", 9.5, "#FFFFFF", 700, "middle")}
  <rect x="{x + 14}" y="{y + 44}" width="236" height="150" rx="6" fill="{PANEL}" stroke="{BORDER}"/>
  <path d="{p_raw}" fill="none" stroke="{MUTED}" stroke-opacity="0.4" stroke-width="0.9"/>
  <path d="{p_al}" fill="none" stroke="{MINT}" stroke-width="2"/>{dots}
  <circle cx="{dc[0]}" cy="{dc[1]}" r="52" fill="{PANEL}" stroke="{BORDER}" stroke-width="2"/>
  <path d="M{dc[0]},{dc[1]} L{dc[0] - 52 * math.sin(math.radians(20)):.1f},{dc[1] - 52 * math.cos(math.radians(20)):.1f} A52,52 0 0,1 {dc[0] + 52 * math.sin(math.radians(20)):.1f},{dc[1] - 52 * math.cos(math.radians(20)):.1f} Z" fill="{MINT}" fill-opacity="0.25"/>
  {hits}
  <line x1="{dc[0]}" y1="{dc[1]}" x2="{dc[0] + 34}" y2="{dc[1] + 14}" stroke="{TEXT}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{dc[0]}" cy="{dc[1]}" r="4" fill="{MINT}"/>
  {T(dc[0], dc[1] - 58, "0° peak", 9, MUTED, 400, "middle")}
  {"".join(f'<rect x="{x + 14 + i * 98}" y="{y + 206}" width="90" height="40" rx="6" fill="{PANEL}" stroke="{BORDER}"/>' for i in range(4))}
  {T(x + 22, y + 220, "IAF", 8.5, MUTED)}{T(x + 22, y + 238, "10.7 Hz", 14, TEXT, 600)}
  {T(x + 120, y + 220, "PHASE LOCKING", 8.5, MUTED)}{T(x + 120, y + 238, "0.95", 14, TEXT, 600)}
  {T(x + 218, y + 220, "FLASHES / S", 8.5, MUTED)}{T(x + 218, y + 238, "9.1", 14, TEXT, 600)}
  {T(x + 316, y + 220, "MEAN ERROR", 8.5, MUTED)}{T(x + 316, y + 238, "+4°", 14, TEXT, 600)}
  <path d="M{x - overhang},{y + h + 26} L{x - 8},{y + h + 8} L{x + w + 8},{y + h + 8} L{x + w + overhang},{y + h + 26} Z" fill="#22323A" stroke="#4A6670" stroke-width="2"/>
  <rect x="{x + w / 2 - 50}" y="{y + h + 12}" width="100" height="6" rx="3" fill="#3A4E57"/>
</g>"""


def callout(n, x, y):
    return (f'<circle cx="{x}" cy="{y}" r="14" fill="{BG}" stroke="{TEXT}" stroke-width="1.8"/>'
            + T(x, y + 5, str(n), 14, TEXT, 700, "middle"))


LEGEND = [
    ("Electrodes", ["Active at Oz over the visual cortex;", "reference + bias on the earlobes."]),
    ("OpenBCI Cyton", ["8-channel biosignal board, 24-bit,", "250 Hz, battery powered."]),
    ("Radio dongle", ["2.4 GHz link to USB. Set the FTDI", "latency timer to 1 ms (≈18 ms lag)."]),
    ("NeuroBack on a laptop", ["BrainFlow → ecHT phase estimate →", "flash scheduled at the target phase."]),
    ("Arduino trigger", ["USB serial: byte 'F' = one 20 ms", "pulse. Pin 7 mirrors it as a marker."]),
    ("Diffused LED", ["White/green light in front of the eyes,", "one flash per alpha cycle (8–13 Hz)."]),
    ("Visual pathway", ["Light → retina → thalamus (LGN) →", "primary visual cortex (V1)."]),
    ("Alpha rhythm", ["Strongest over the occipital cortex,", "recorded at Oz: the loop closes."]),
]


def hardware(x, fs, alpha, trig):
    W, H = 1800, 1000
    tx, ty, s = 120, 176, 1.08
    G = lambda p: local_to_global(p, tx, ty, s)  # noqa: E731
    eye, oz, ear, v1 = G(EYE), G(OZ), G(EAR), G(V1)
    lgn = G((140, 162))
    ledx, ledy = 560, eye[1] - 4
    cy_c = (300, 736)
    lap = (962, 400, 400, 255)
    base_y = lap[1] + lap[3]
    ard = (620, 640)
    dongle = (lap[0] - 34 - 50, base_y + 9)

    legend = "".join(
        callout(i + 1, 1440, 196 + i * 86) + T(1466, 202 + i * 86, t, 17, TEXT, 600)
        + T(1466, 226 + i * 86, d[0], 13.5, MUTED) + T(1466, 245 + i * 86, d[1], 13.5, MUTED)
        for i, (t, d) in enumerate(LEGEND))
    p_raw, p_al, flashes = eeg_paths(x, fs, alpha, trig, t0=40.0, dur=0.62, x0=90, x1=560, yc=958, amp=15, raw_amp=0.0)
    timing_flashes = "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4.2" fill="{FLASH}" filter="url(#glow)"/>' for a, b in flashes)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
{defs()}
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect x="1400" y="130" width="370" height="730" rx="14" fill="{PANEL}" stroke="{BORDER}"/>
{T(1430, 166, "THE CLOSED LOOP", 12, MUTED, 700, "start", 'letter-spacing="2"')}
{legend}
{T(60, 70, "How NeuroBack is wired", 36, TEXT, 700)}
{T(62, 104, "One loop per alpha cycle: brain → EEG → laptop → Arduino → light → eyes → brain", 17, MUTED)}

<!-- light beam to the eye -->
<polygon points="{ledx - 12},{ledy - 10} {ledx - 12},{ledy + 10} {eye[0] + 4:.1f},{eye[1] + 22:.1f} {eye[0] + 4:.1f},{eye[1] - 22:.1f}" fill="url(#beam)"/>
{"".join(f'<line x1="{ledx - 14}" y1="{ledy + o * 0.25:.1f}" x2="{eye[0] + 8:.1f}" y2="{eye[1] + o:.1f}" stroke="{FLASH}" stroke-opacity="0.35" stroke-width="1"/>' for o in (-16, 0, 16))}
{T(eye[0] + 70, ledy - 42, "20 ms flash at the", 13, FLASH, 600, "start")}
{T(eye[0] + 70, ledy - 25, "target alpha phase", 13, FLASH, 600, "start")}

{head_group("hw", tx, ty, s)}
<!-- alpha waves leaving the occipital cortex -->
{"".join(f'<path d="M{oz[0] - 16 - 12 * k:.1f},{oz[1] - 26 - 8 * k:.1f} q-{10 + 4 * k},{26 + 8 * k} 0,{52 + 16 * k}" fill="none" stroke="{MINT}" stroke-opacity="{0.7 - 0.2 * k:.2f}" stroke-width="2.2"/>' for k in range(3))}
{T(oz[0] - 64, oz[1] - 70, "alpha 8–13 Hz", 13, MINT, 600, "middle")}
{T(v1[0] + 32, v1[1] - 46, "V1", 14, MINT, 700, "start")}
<line x1="{v1[0] + 6:.1f}" y1="{v1[1] - 6:.1f}" x2="{v1[0] + 28:.1f}" y2="{v1[1] - 40:.1f}" stroke="{MINT}" stroke-opacity="0.6"/>
{T(lgn[0] + 4, lgn[1] - 74, "LGN", 13, FLASH, 600, "middle")}
<line x1="{lgn[0]:.1f}" y1="{lgn[1] - 6:.1f}" x2="{lgn[0] + 2:.1f}" y2="{lgn[1] - 68:.1f}" stroke="{FLASH}" stroke-opacity="0.6"/>
{T(eye[0] - 2, eye[1] + 44, "retina", 13, FLASH, 600, "middle")}
<line x1="{eye[0]:.1f}" y1="{eye[1] + 8:.1f}" x2="{eye[0] - 2:.1f}" y2="{eye[1] + 30:.1f}" stroke="{FLASH}" stroke-opacity="0.6"/>

<!-- electrode wires to the Cyton -->
<path d="M{oz[0]:.1f},{oz[1] + 8:.1f} C{oz[0] - 50:.1f},{oz[1] + 150:.1f} 170,{cy_c[1] - 160} {cy_c[0] - 20},{cy_c[1] - 70}" fill="none" stroke="{MINT}" stroke-width="3"/>
<path d="M{ear[0]:.1f},{ear[1] + 6:.1f} C{ear[0] - 10:.1f},{ear[1] + 110:.1f} {cy_c[0] + 30},{cy_c[1] - 150} {cy_c[0] + 20},{cy_c[1] - 70}" fill="none" stroke="#C9D6DA" stroke-width="3"/>
{cyton(*cy_c)}
{T(cy_c[0], cy_c[1] + 112, "OpenBCI Cyton", 15, TEXT, 600, "middle")}
{T(cy_c[0], cy_c[1] + 131, "8 ch · 24-bit · 250 Hz", 12, MUTED, 400, "middle")}

<!-- LED on its stand + Arduino -->
<rect x="{ledx + 22}" y="{ledy + 22}" width="8" height="{ard[1] - ledy - 52}" fill="#2C3E46"/>
<rect x="{ledx - 12}" y="{ard[1] - 30}" width="80" height="10" rx="4" fill="#2C3E46"/>
{led(ledx, ledy, "left", 1.0)}
<path d="M{ard[0] + 40},{ard[1]} C{ard[0] + 40},{ard[1] - 60} {ledx + 50},{ledy + 120} {ledx + 30},{ledy + 24}" fill="none" stroke="{RED}" stroke-width="2.4"/>
<path d="M{ard[0] + 52},{ard[1]} C{ard[0] + 52},{ard[1] - 50} {ledx + 58},{ledy + 130} {ledx + 34},{ledy + 24}" fill="none" stroke="#9AA9AF" stroke-width="2.4"/>
{T(ledx + 8, ledy + 150, "pin 9", 12, MUTED, 400, "end")}
{T(ledx + 8, ledy + 166, "20 ms pulse", 12, MUTED, 400, "end")}
{arduino(*ard)}
{T(ard[0] + 88, ard[1] + 132, "Arduino trigger", 15, TEXT, 600, "middle")}
{T(ard[0] + 88, ard[1] + 151, "firmware/neuroback_trigger", 12, MUTED, 400, "middle")}

<!-- laptop -->
{laptop(*lap, x, fs, alpha, trig)}
{T(lap[0] + lap[2] / 2, base_y + 117, "Laptop running NeuroBack", 15, TEXT, 600, "middle")}
{T(lap[0] + lap[2] / 2, base_y + 136, "BrainFlow · ecHT phase tracking · sub-ms scheduler", 12, MUTED, 400, "middle")}

<!-- dongle plugged into the laptop + RF link -->
<rect x="{dongle[0]}" y="{dongle[1]}" width="44" height="16" rx="3" fill="#E3ECEE" stroke="#9FB6BD"/>
<rect x="{dongle[0] + 44}" y="{dongle[1] + 4}" width="12" height="8" fill="#B9C4C9"/>
<circle cx="{dongle[0] + 10}" cy="{dongle[1] + 8}" r="2.5" fill="{BLUE}"/>
{T(dongle[0] + 30, dongle[1] - 12, "USB dongle", 12, MUTED, 400, "middle")}
<path d="M{cy_c[0] + 92},{cy_c[1] + 6} C{cy_c[0] + 220},{cy_c[1] + 165} {dongle[0] - 40},{cy_c[1] + 165} {dongle[0] - 4},{dongle[1] + 9}" fill="none" stroke="{BLUE}" stroke-width="2.2" stroke-dasharray="3 7" stroke-linecap="round"/>
{"".join(f'<path d="M{cy_c[0] + 96 + 9 * k},{cy_c[1] - 18 - 9 * k} a{12 + 9 * k},{12 + 9 * k} 0 0,1 0,{24 + 18 * k}" fill="none" stroke="{BLUE}" stroke-opacity="{0.8 - 0.22 * k:.2f}" stroke-width="2"/>' for k in range(3))}
{T(610, cy_c[1] + 132, "2.4 GHz radio · EEG samples at 250 Hz", 13, BLUE, 600, "middle")}

<!-- Arduino -> laptop USB serial -->
<path d="M{ard[0] + 194},{ard[1] + 48} C{ard[0] + 260},{ard[1] + 48} {lap[0]},{base_y + 82} {lap[0] + 80},{base_y + 26}" fill="none" stroke="#C9D6DA" stroke-width="3"/>
{T(958, base_y + 87, "USB serial · byte 'F' = flash", 12.5, TEXT, 600)}

{callout(1, oz[0] - 22, oz[1] + 40)}
{callout(2, cy_c[0] - 104, cy_c[1] - 40)}
{callout(3, dongle[0] - 26, dongle[1] - 26)}
{callout(4, lap[0] - 30, lap[1] - 20)}
{callout(5, ard[0] - 24, ard[1] + 24)}
{callout(6, ledx + 54, ledy - 38)}
{callout(7, lgn[0] - 34, lgn[1] + 44)}
{callout(8, v1[0] + 6, v1[1] + 52)}

<!-- timing strip -->
<rect x="60" y="900" width="1320" height="86" rx="12" fill="{PANEL}" stroke="{BORDER}"/>
{T(84, 922, "ONE CYCLE ≈ 100 ms", 11.5, MUTED, 700, "start", 'letter-spacing="2"')}
<path d="{p_al}" fill="none" stroke="{MINT}" stroke-width="2.4"/>{timing_flashes}
{T(600, 926, "① sample reaches the laptop ≈ 18 ms after it is recorded (Cyton, FTDI 1 ms fix)", 13.5, TEXT)}
{T(600, 948, "② ecHT estimates the phase now, in &lt; 1 ms; the next peak is predicted from the alpha frequency", 13.5, TEXT)}
{T(600, 970, "③ the flash is scheduled ahead of the peak, minus the measured output latency, so the light lands on target", 13.5, TEXT)}
</svg>"""
    render(svg, W, H, ASSETS / "hardware-setup.png", scale=1.5)


def main():
    x, fs, alpha, trig = real_eeg()
    hero(x, fs, alpha, trig)
    hardware(x, fs, alpha, trig)
    print("wrote", ASSETS / "hero.png", ASSETS / "social-preview.png", ASSETS / "hardware-setup.png")


if __name__ == "__main__":
    main()
