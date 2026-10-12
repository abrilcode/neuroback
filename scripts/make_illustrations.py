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

# Light, journal-style palette (matches the README charts).
BG, PANEL, PANEL2, BORDER = "#FFFFFF", "#F4F7FB", "#E8EFF7", "#D5DEE8"
TEXT, MUTED = "#0F2742", "#5B6F86"
NAVY, BLUE, PALE, SKY, RED = "#0B3C7A", "#3A7FC1", "#8DB4D9", "#0EA5E9", "#C2412D"
MINT, FLASH = NAVY, SKY  # brain/EEG = navy, light stimulus = sky blue
SKIN, SKIN2, SKIN_LINE = "#EEF4FA", "#E3ECF6", "#8FAAC6"
BRAIN_FILL = "#DCE9F6"
FONT = "'Helvetica Neue', Helvetica, 'Segoe UI', sans-serif"

# ----------------------------------------------------------------------------- head + brain
# Local coordinates: a head in profile facing right, about 310 x 380. Anatomical layout
# follows a standard lateral view: frontal, parietal, temporal and occipital lobes split
# by the central sulcus and the lateral (Sylvian) fissure, cerebellum, brainstem, cord.
HEAD = ("M110,380 C106,352 98,326 86,302 C52,268 24,220 24,158 C24,82 86,20 162,18 "
        "C228,16 268,58 272,110 C273,124 271,136 275,146 C280,158 292,178 300,194 "
        "C304,201 302,209 292,211 C287,212 285,215 286,220 C290,225 289,232 284,235 "
        "C286,238 286,243 282,246 C287,251 285,258 279,261 C281,268 282,277 274,284 "
        "C266,292 252,295 238,295 C222,295 210,300 204,310 C199,330 198,355 200,380 Z")
BRAIN = ("M250,122 C254,74 216,32 164,30 C108,27 58,52 42,96 C30,124 30,156 42,170 "
         "C55,184 77,186 96,182 C121,196 158,202 186,194 C206,188 222,178 220,166 "
         "C236,160 249,146 250,122 Z")
CEREBELLUM = "M82,182 C68,191 70,218 93,225 C116,231 138,222 140,206 C138,193 118,185 98,183 Z"
BRAINSTEM = ("M126,188 C136,208 138,236 134,270 C133,282 131,292 129,302 L119,302 "
             "C120,288 120,276 119,264 C118,232 115,210 108,196 Z")
CORD = "M119,302 L129,302 L127,380 L121,380 Z"
EAR_PATH = ("M186,172 C182,162 162,160 156,176 C151,190 155,206 160,216 C163,224 164,232 172,234 "
            "C180,236 183,228 182,222 C184,216 190,210 189,202 C188,194 190,182 186,172 Z")
SULCI_MAJOR = ("M142,31 C146,55 158,72 156,95 C155,112 165,124 172,140",
               "M216,166 C196,156 172,146 150,134 C138,128 126,124 116,124")
SULCI = ("M162,32 C167,56 176,74 175,98 C175,116 183,128 190,146",
         "M124,37 C128,60 139,74 137,96 C136,112 144,122 150,131",
         "M238,86 C222,68 202,60 180,62", "M246,118 C230,104 210,98 190,100",
         "M224,142 C212,132 200,128 190,128", "M128,74 C112,76 98,86 90,104",
         "M108,48 C100,58 94,70 92,82", "M211,180 C187,172 157,162 122,148",
         "M190,192 C166,188 140,180 110,166", "M72,62 C62,88 60,116 66,146",
         "M54,94 C48,114 48,134 54,160", "M112,104 C104,110 100,120 102,130")
FOLIA = ("M84,197 C101,191 121,194 138,202", "M80,207 C100,203 122,205 140,212", "M85,217 C101,215 119,217 133,221")
EYE = (255.0, 155.0)
OZ = (21.0, 146.0)
EAR = (173.0, 239.0)  # earlobe: reference electrode
V1 = (44.0, 144.0)
LGN = (142.0, 165.0)
PATHWAY = "M249,157 C228,164 204,168 182,168 C164,168 153,166 142,165 C117,160 82,151 45,144"


def head_group(uid: str, tx: float, ty: float, s: float, mirror: bool = False, labels: bool = True) -> str:
    sx = -s if mirror else s
    sulci = "".join(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-opacity="0.45" stroke-width="1.3" stroke-linecap="round"/>' for d in SULCI)
    major = "".join(f'<path d="{d}" fill="none" stroke="{NAVY}" stroke-opacity="0.55" stroke-width="2" stroke-linecap="round"/>' for d in SULCI_MAJOR)
    folia = "".join(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-opacity="0.4" stroke-width="1.1"/>' for d in FOLIA)
    return f"""
<g transform="translate({tx},{ty}) scale({sx},{s})">
  <defs>
    <clipPath id="brainclip-{uid}"><path d="{BRAIN}"/></clipPath>
    <clipPath id="cbclip-{uid}"><path d="{CEREBELLUM}"/></clipPath>
    <radialGradient id="occ-{uid}" cx="{V1[0]}" cy="{V1[1]}" r="62" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{BLUE}" stop-opacity="0.55"/>
      <stop offset="0.6" stop-color="{BLUE}" stop-opacity="0.14"/>
      <stop offset="1" stop-color="{BLUE}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="neckfade-{uid}" x1="0" y1="0" x2="0" y2="380" gradientUnits="userSpaceOnUse">
      <stop offset="0.8" stop-color="#FFFFFF"/><stop offset="1" stop-color="#000000"/>
    </linearGradient>
    <mask id="neckmask-{uid}" maskUnits="userSpaceOnUse" x="-20" y="-20" width="360" height="410">
      <rect x="-20" y="-20" width="360" height="410" fill="url(#neckfade-{uid})"/>
    </mask>
    <linearGradient id="brainfill-{uid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#E6EFF9"/><stop offset="1" stop-color="#D6E5F5"/>
    </linearGradient>
    <linearGradient id="cord-{uid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#D6E5F5" stop-opacity="1"/><stop offset="1" stop-color="#D6E5F5" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="skin-{uid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#F3F7FC"/><stop offset="1" stop-color="#E4EDF7"/>
    </linearGradient>
  </defs>
  <g mask="url(#neckmask-{uid})">
    <path d="{HEAD}" fill="url(#skin-{uid})" stroke="{SKIN_LINE}" stroke-width="2" stroke-linejoin="round"/>
    <path d="{CORD}" fill="url(#cord-{uid})"/>
  </g>
  <path d="{BRAINSTEM}" fill="#DCE8F5" stroke="{BLUE}" stroke-opacity="0.6" stroke-width="1.4"/>
  <path d="{CEREBELLUM}" fill="#D3E3F4" stroke="{BLUE}" stroke-opacity="0.7" stroke-width="1.5"/>
  <g clip-path="url(#cbclip-{uid})">{folia}</g>
  <g clip-path="url(#brainclip-{uid})">
    <rect x="0" y="0" width="320" height="260" fill="url(#brainfill-{uid})"/>
    <rect x="0" y="0" width="320" height="260" fill="url(#occ-{uid})"/>
    {sulci}{major}
  </g>
  <path d="{BRAIN}" fill="none" stroke="{BLUE}" stroke-opacity="0.85" stroke-width="1.8" stroke-linejoin="round"/>
  <path d="M238,295 C214,292 194,281 184,262" fill="none" stroke="{SKIN_LINE}" stroke-opacity="0.7" stroke-width="1.4" stroke-linecap="round"/>
  <path d="{EAR_PATH}" fill="#E8F0F8" stroke="{SKIN_LINE}" stroke-width="1.6" stroke-linejoin="round"/>
  <path d="M180,176 C168,172 162,184 164,196 C165,204 170,210 172,218" fill="none" stroke="{SKIN_LINE}" stroke-width="1.3" stroke-linecap="round"/>
  <ellipse cx="178" cy="199" rx="5" ry="8" fill="#D5E2EF"/>
  <path d="M240,139 Q252,133 266,140" fill="none" stroke="{SKIN_LINE}" stroke-width="2.2" stroke-linecap="round"/>
  <path d="M247,151 Q256,147 263,155 Q256,161 247,159" fill="#FFFFFF" stroke="#6F8DAE" stroke-width="1.4" stroke-linejoin="round"/>
  <circle cx="{EYE[0] + 1}" cy="{EYE[1]}" r="2.6" fill="{NAVY}"/>
  <path d="M289,207 Q283,202 278,206" fill="none" stroke="{SKIN_LINE}" stroke-width="1.4" stroke-linecap="round"/>
  <path d="M282,240 L273,241" stroke="{SKIN_LINE}" stroke-width="1.4" stroke-linecap="round"/>
  <path d="{PATHWAY}" fill="none" stroke="{FLASH}" stroke-width="2.6" stroke-dasharray="6 5" stroke-linecap="round"/>
  <circle cx="{V1[0]}" cy="{V1[1]}" r="5.5" fill="{NAVY}" stroke="#FFFFFF" stroke-width="1.5"/>
  <circle cx="{LGN[0]}" cy="{LGN[1]}" r="4" fill="{FLASH}" stroke="#FFFFFF" stroke-width="1.2"/>
  <circle cx="{OZ[0]}" cy="{OZ[1]}" r="8" fill="#FFFFFF" stroke="{NAVY}" stroke-width="3"/>
  <circle cx="{OZ[0]}" cy="{OZ[1]}" r="3" fill="{NAVY}"/>
  <rect x="{EAR[0] - 6}" y="{EAR[1] - 4}" width="12" height="9" rx="2" fill="#FFFFFF" stroke="{NAVY}" stroke-width="1.5"/>
</g>"""


def preview_head(out):
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="700" height="800" viewBox="0 0 700 800">{defs()}
<rect width="700" height="800" fill="#FFFFFF"/>{head_group("pv", 30, 20, 2.0)}</svg>"""
    render(svg, 700, 800, out, scale=1.0)


def local_to_global(p, tx, ty, s, mirror=False):
    return (tx - s * p[0], ty + s * p[1]) if mirror else (tx + s * p[0], ty + s * p[1])


# ----------------------------------------------------------------------------- shared defs
def defs() -> str:
    return f"""
<defs>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="bigglow" x="-100%" y="-100%" width="300%" height="300%">
    <feGaussianBlur stdDeviation="10" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <radialGradient id="bgglow" cx="0.8" cy="0.3" r="0.7">
    <stop offset="0" stop-color="#EEF5FC"/><stop offset="1" stop-color="#FFFFFF"/>
  </radialGradient>
  <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
    <path d="M24,0 L0,0 0,24" fill="none" stroke="#E6EDF5" stroke-width="1"/>
  </pattern>
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
    <path d="M0,0 L10,5 L0,10 z" fill="{SKY}"/>
  </marker>
</defs>"""


def led(x, y, facing="left", s=1.0) -> str:
    """LED module with diffuser. (x, y) = centre of the emitting face."""
    d = -1 if facing == "left" else 1
    hx = x if facing == "left" else x - 56 * s
    return f"""
<g>
  <rect x="{hx + (6 if facing == 'left' else 0) * s}" y="{y - 22 * s}" width="{50 * s}" height="{44 * s}" rx="{8 * s}" fill="#E8EEF5" stroke="#7F95AD" stroke-width="1.5"/>
  <rect x="{x - (4 if facing == 'left' else -1) * s}" y="{y - 19 * s}" width="{4 * s}" height="{38 * s}" rx="{2 * s}" fill="#FFFFFF" fill-opacity="0.55"/>
  <circle cx="{x + d * 2 * s}" cy="{y}" r="{11 * s}" fill="{FLASH}" filter="url(#bigglow)"/>
  <circle cx="{x + d * 2 * s}" cy="{y}" r="{6 * s}" fill="#E0F6FF"/>
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
    tx, ty, s = 1190, 30, 0.84  # participant's head, facing left
    eye = local_to_global(EYE, tx, ty, s, True)
    oz = local_to_global(OZ, tx, ty, s, True)
    v1 = local_to_global(V1, tx, ty, s, True)
    lgn = local_to_global(LGN, tx, ty, s, True)
    ledx, ledy = 790, eye[1] - 2

    # two-track figure: EEG (Oz) and the light stimulus, on a shared time axis
    x0, x1, t0, dur = 150, 1230, 20.0, 2.4
    eeg_y, stim_y = 452, 560
    p_raw, p_al, flashes = eeg_paths(x, fs, alpha, trig, t0=t0, dur=dur, x0=x0, x1=x1, yc=eeg_y, amp=38, raw_amp=0.55)
    px_per_s = (x1 - x0) / dur
    pulse_w = 0.020 * px_per_s  # 20 ms pulses
    guides = "".join(f'<line x1="{a:.1f}" y1="{b + 8:.1f}" x2="{a:.1f}" y2="{stim_y - 14}" stroke="{SKY}" stroke-opacity="0.35" '
                     f'stroke-width="1" stroke-dasharray="2 3"/>' for a, b in flashes)
    dots = "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="7" fill="{SKY}" fill-opacity="0.18"/>'
                   f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.6" fill="{SKY}" stroke="#FFFFFF" stroke-width="1.2"/>' for a, b in flashes)
    pulses = "".join(f'<rect x="{a:.1f}" y="{stim_y - 13}" width="{pulse_w:.1f}" height="26" rx="1.5" fill="{SKY}"/>' for a, _ in flashes)
    sb_x = x1 - 0.2 * px_per_s
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
{defs()}
<rect width="{W}" height="{H}" fill="url(#bgglow)"/>

<!-- stimulus beam: LED to the participant's eye -->
<polygon points="{ledx + 10},{ledy - 9} {ledx + 10},{ledy + 9} {eye[0] - 2:.1f},{eye[1] + 14:.1f} {eye[0] - 2:.1f},{eye[1] - 14:.1f}" fill="url(#beamR)"/>
{led(ledx, ledy, facing="right", s=1.0)}
{head_group("hero", tx, ty, s, mirror=True)}

<!-- labels: stimulus, participant, brain -->
{T(ledx - 6, ledy - 46, "VISUAL STIMULUS", 11.5, SKY, 700, "middle", 'letter-spacing="1.5"')}
{T(ledx - 6, ledy + 50, "20 ms LED flash", 12.5, TEXT, 600, "middle")}
{T(ledx - 6, ledy + 66, "at the alpha peak", 12, MUTED, 400, "middle")}
{T(tx - 150 * s, ty + 8, "PARTICIPANT", 11.5, NAVY, 700, "middle", 'letter-spacing="1.5"')}
<path d="M{v1[0] + 3:.1f},{v1[1] - 5:.1f} L{v1[0] + 22:.1f},{v1[1] - 60:.1f} L{W - 12},{v1[1] - 60:.1f}" fill="none" stroke="{NAVY}" stroke-opacity="0.55" stroke-width="1"/>
{T(W - 12, v1[1] - 66, "visual cortex (V1)", 12, NAVY, 600, "end")}
{T(eye[0] - 30, eye[1] - 22, "retina → LGN → V1", 12, SKY, 600, "end")}
{T(oz[0] + 14, oz[1] + 5, "Oz", 12, NAVY, 700, "start")}

<!-- closed loop connectors -->
<path d="M{oz[0]:.1f},{oz[1] + 9:.1f} C{oz[0] + 26:.1f},{oz[1] + 120:.1f} {x1 + 18},{eeg_y - 120} {x1 + 4},{eeg_y - 10}"
      fill="none" stroke="{NAVY}" stroke-width="1.6" stroke-dasharray="3 4" marker-end="url(#arrow)"/>

<!-- title -->
{T(60, 108, "NeuroBack", 78, NAVY, 700)}
{T(63, 160, "Closed-loop visual stimulation", 27, TEXT, 400)}
{T(63, 194, "phase-locked to the EEG alpha rhythm", 27, TEXT, 400)}
{T(64, 236, "OpenBCI Cyton · ecHT phase tracking · 109-subject EEG benchmark · Python", 14, MUTED)}

<!-- tracks -->
{T(60, eeg_y - 4, "EEG", 13, TEXT, 700)}{T(60, eeg_y + 13, "Oz, 8–13 Hz", 11, MUTED)}
{T(60, stim_y - 4, "Stimulus", 13, TEXT, 700)}{T(60, stim_y + 13, "LED pulses", 11, MUTED)}
<line x1="{x0}" y1="{stim_y + 13}" x2="{x1}" y2="{stim_y + 13}" stroke="{BORDER}" stroke-width="1"/>
<path d="{p_raw}" fill="none" stroke="#9FB1C4" stroke-opacity="0.7" stroke-width="1"/>
<path d="{p_al}" fill="none" stroke="{NAVY}" stroke-width="2.2" stroke-linecap="round"/>
{guides}{dots}{pulses}
<line x1="{sb_x:.1f}" y1="{stim_y + 34}" x2="{x1}" y2="{stim_y + 34}" stroke="{TEXT}" stroke-width="2"/>
{T((sb_x + x1) / 2, stim_y + 52, "200 ms", 11, MUTED, 400, "middle")}
{T(x0, 622, "Real EEG (PhysioNet S004, Oz). Each flash was scheduled causally by the ecHT closed loop, aimed at the alpha peak.", 11, MUTED)}
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
  <polygon points="{pts}" fill="#F7FAFC" stroke="#8FA3B8" stroke-width="2"/>
  <rect x="{cx - 60}" y="{cy - 70}" width="120" height="16" rx="3" fill="#1B2A30"/>{pins}
  <rect x="{cx - 26}" y="{cy - 22}" width="46" height="46" rx="4" fill="#1B2A30"/>
  <rect x="{cx - 19}" y="{cy - 15}" width="32" height="32" rx="3" fill="#24363D"/>
  <rect x="{cx + 32}" y="{cy - 6}" width="26" height="30" rx="3" fill="#1B2A30"/>
  <rect x="{cx - 56}" y="{cy + 34}" width="22" height="12" rx="2" fill="#1B2A30"/>
  <circle cx="{cx - 50}" cy="{cy}" r="9" fill="none" stroke="#9FB6BD" stroke-width="1.5"/>
  <circle cx="{cx + 50}" cy="{cy + 46}" r="5" fill="none" stroke="#9FB6BD" stroke-width="1.5"/>
  {T(cx, cy + 66, "OpenBCI", 11, "#5B6F86", 700, "middle")}
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
    p_raw, p_al, flashes = eeg_paths(x_eeg, fs, alpha, trig, t0=31.0, dur=1.6, x0=x + 22, x1=x + 240, yc=y + 112, amp=30, raw_amp=0.6)
    dots = "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.2" fill="{SKY}" stroke="#FFFFFF" stroke-width="1"/>' for a, b in flashes)
    pulses = "".join(f'<rect x="{a - 1.5:.1f}" y="{y + 168}" width="3.5" height="12" rx="1" fill="{SKY}"/>' for a, _ in flashes)
    dc = (x + 318, y + 118)
    hits = "".join(
        f'<circle cx="{dc[0] + 44 * math.sin(math.radians(a)):.1f}" cy="{dc[1] - 44 * math.cos(math.radians(a)):.1f}" r="2.6" fill="{SKY}"/>'
        for a in np.random.default_rng(2).normal(4, 22, 24))
    return f"""
<g>
  <rect x="{x - 8}" y="{y - 8}" width="{w + 16}" height="{h + 16}" rx="12" fill="#DDE5EE" stroke="#8FA3B8" stroke-width="2"/>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="#F6F8FB"/>
  <rect x="{x}" y="{y}" width="{w}" height="30" fill="#FFFFFF"/>
  <line x1="{x}" y1="{y + 30}" x2="{x + w}" y2="{y + 30}" stroke="{BORDER}"/>
  {T(x + 14, y + 20, "NeuroBack", 13, NAVY, 700)}
  <rect x="{x + 96}" y="{y + 8}" width="92" height="15" rx="7" fill="{PANEL2}"/>
  {T(x + 142, y + 19, "Cyton · 250 Hz", 9, MUTED, 400, "middle")}
  <rect x="{x + w - 58}" y="{y + 7}" width="46" height="17" rx="5" fill="{RED}"/>
  {T(x + w - 35, y + 19, "STOP", 9.5, "#FFFFFF", 700, "middle")}
  <rect x="{x + 14}" y="{y + 44}" width="236" height="150" rx="6" fill="#FFFFFF" stroke="{BORDER}"/>
  <path d="{p_raw}" fill="none" stroke="#A9B8C8" stroke-width="0.9"/>
  <path d="{p_al}" fill="none" stroke="{NAVY}" stroke-width="1.8"/>{dots}{pulses}
  <circle cx="{dc[0]}" cy="{dc[1]}" r="52" fill="#FFFFFF" stroke="{BORDER}" stroke-width="2"/>
  <path d="M{dc[0]},{dc[1]} L{dc[0] - 52 * math.sin(math.radians(20)):.1f},{dc[1] - 52 * math.cos(math.radians(20)):.1f} A52,52 0 0,1 {dc[0] + 52 * math.sin(math.radians(20)):.1f},{dc[1] - 52 * math.cos(math.radians(20)):.1f} Z" fill="{BLUE}" fill-opacity="0.18"/>
  {hits}
  <line x1="{dc[0]}" y1="{dc[1]}" x2="{dc[0] + 34}" y2="{dc[1] + 14}" stroke="{NAVY}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="{dc[0]}" cy="{dc[1]}" r="4" fill="{NAVY}"/>
  {T(dc[0], dc[1] - 58, "0° peak", 9, MUTED, 400, "middle")}
  {"".join(f'<rect x="{x + 14 + i * 98}" y="{y + 206}" width="90" height="40" rx="6" fill="#FFFFFF" stroke="{BORDER}"/>' for i in range(4))}
  {T(x + 22, y + 220, "IAF", 8.5, MUTED)}{T(x + 22, y + 238, "10.7 Hz", 14, TEXT, 600)}
  {T(x + 120, y + 220, "PHASE LOCKING", 8.5, MUTED)}{T(x + 120, y + 238, "0.95", 14, TEXT, 600)}
  {T(x + 218, y + 220, "FLASHES / S", 8.5, MUTED)}{T(x + 218, y + 238, "9.1", 14, TEXT, 600)}
  {T(x + 316, y + 220, "MEAN ERROR", 8.5, MUTED)}{T(x + 316, y + 238, "+4°", 14, TEXT, 600)}
  <path d="M{x - overhang},{y + h + 26} L{x - 8},{y + h + 8} L{x + w + 8},{y + h + 8} L{x + w + overhang},{y + h + 26} Z" fill="#DDE5EE" stroke="#8FA3B8" stroke-width="2"/>
  <rect x="{x + w / 2 - 50}" y="{y + h + 12}" width="100" height="6" rx="3" fill="#B8C6D4"/>
</g>"""


def callout(n, x, y):
    return (f'<circle cx="{x}" cy="{y}" r="14" fill="{NAVY}"/>'
            + T(x, y + 5, str(n), 13.5, "#FFFFFF", 700, "middle"))


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
    lgn = G(LGN)
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
<rect width="{W}" height="{H}" fill="#FFFFFF"/>
<rect width="{W}" height="{H}" fill="url(#grid)" opacity="0.6"/>
<rect x="1400" y="130" width="370" height="730" rx="14" fill="{PANEL}" stroke="{BORDER}"/>
{T(1430, 166, "THE CLOSED LOOP", 12, MUTED, 700, "start", 'letter-spacing="2"')}
{legend}
{T(60, 70, "How NeuroBack is wired", 36, NAVY, 700)}
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
<path d="M{ear[0]:.1f},{ear[1] + 6:.1f} C{ear[0] - 10:.1f},{ear[1] + 110:.1f} {cy_c[0] + 30},{cy_c[1] - 150} {cy_c[0] + 20},{cy_c[1] - 70}" fill="none" stroke="#8FA3B8" stroke-width="3"/>
{cyton(*cy_c)}
{T(cy_c[0], cy_c[1] + 112, "OpenBCI Cyton", 15, TEXT, 600, "middle")}
{T(cy_c[0], cy_c[1] + 131, "8 ch · 24-bit · 250 Hz", 12, MUTED, 400, "middle")}

<!-- LED on its stand + Arduino -->
<rect x="{ledx + 22}" y="{ledy + 22}" width="8" height="{ard[1] - ledy - 52}" fill="#AEBCCB"/>
<rect x="{ledx - 12}" y="{ard[1] - 30}" width="80" height="10" rx="4" fill="#AEBCCB"/>
{led(ledx, ledy, "left", 1.0)}
<path d="M{ard[0] + 40},{ard[1]} C{ard[0] + 40},{ard[1] - 60} {ledx + 50},{ledy + 120} {ledx + 30},{ledy + 24}" fill="none" stroke="{RED}" stroke-width="2.4"/>
<path d="M{ard[0] + 52},{ard[1]} C{ard[0] + 52},{ard[1] - 50} {ledx + 58},{ledy + 130} {ledx + 34},{ledy + 24}" fill="none" stroke="#5B6F86" stroke-width="2.4"/>
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
<rect x="{dongle[0]}" y="{dongle[1]}" width="44" height="16" rx="3" fill="#F7FAFC" stroke="#8FA3B8"/>
<rect x="{dongle[0] + 44}" y="{dongle[1] + 4}" width="12" height="8" fill="#B9C4C9"/>
<circle cx="{dongle[0] + 10}" cy="{dongle[1] + 8}" r="2.5" fill="{BLUE}"/>
{T(dongle[0] + 30, dongle[1] - 12, "USB dongle", 12, MUTED, 400, "middle")}
<path d="M{cy_c[0] + 92},{cy_c[1] + 6} C{cy_c[0] + 220},{cy_c[1] + 165} {dongle[0] - 40},{cy_c[1] + 165} {dongle[0] - 4},{dongle[1] + 9}" fill="none" stroke="{BLUE}" stroke-width="2.2" stroke-dasharray="3 7" stroke-linecap="round"/>
{"".join(f'<path d="M{cy_c[0] + 96 + 9 * k},{cy_c[1] - 18 - 9 * k} a{12 + 9 * k},{12 + 9 * k} 0 0,1 0,{24 + 18 * k}" fill="none" stroke="{BLUE}" stroke-opacity="{0.8 - 0.22 * k:.2f}" stroke-width="2"/>' for k in range(3))}
{T(610, cy_c[1] + 132, "2.4 GHz radio · EEG samples at 250 Hz", 13, BLUE, 600, "middle")}

<!-- Arduino -> laptop USB serial -->
<path d="M{ard[0] + 194},{ard[1] + 48} C{ard[0] + 260},{ard[1] + 48} {lap[0]},{base_y + 82} {lap[0] + 80},{base_y + 26}" fill="none" stroke="#7F95AD" stroke-width="3"/>
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
