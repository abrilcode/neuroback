"""Command-line entry point: ``neuroback {gui,demo,benchmark,screenshots}``."""

from __future__ import annotations

import argparse
import sys


def _source(args):
    from .sources import ArrayPlayback, BrainFlowSource, SimulatedAlpha

    if args.board == "simulated":
        return SimulatedAlpha()
    if args.board == "playback":
        import numpy as np

        from .bench.physionet import fetch, occipital_channel
        from .dsp import resample

        path = fetch([args.subject], verbose=True)[0]
        x, fs, ch = occipital_channel(path)
        return ArrayPlayback(resample(x, fs, 250.0), 250.0, label=f"PhysioNet S{args.subject:03d} {ch}")
    return BrainFlowSource(args.board, serial_port=args.port or "", channel=args.channel)


def cmd_gui(args):
    from .gui.app import main
    from .stimulators import SerialTrigger

    stim = SerialTrigger(args.trigger_port) if args.trigger_port else None
    return main(_source(args), stim, latency_ms=args.latency_ms, estimator=args.estimator)


def cmd_demo(args):
    """Headless closed loop on simulated alpha; prints how well flashes hit the target."""
    from .analysis import circ_mean_deg, circ_sd_deg, phase_at, plv, wrap
    from .closedloop import ClosedLoop, run_offline
    from .dsp import individual_alpha_frequency, offline_phase
    from .phase import EcHT
    from .simulate import alpha_eeg

    import math

    fs = 250.0
    x = alpha_eeg(args.seconds, fs, iaf=10.3, seed=args.seed)
    iaf = individual_alpha_frequency(x, fs).freq
    truth, _, _ = offline_phase(x, fs, iaf)
    t = run_offline(x, fs, ClosedLoop(fs, EcHT(fs, iaf), f0=iaf, target_deg=args.target), chunk=4)
    err = wrap(phase_at(t, truth, fs) - math.radians(args.target))
    print(f"IAF {iaf:.2f} Hz | {len(t)} flashes in {args.seconds:g} s | target {args.target:g}°")
    print(f"phase-locking value {plv(err):.2f} | mean error {circ_mean_deg(err):+.1f}° | circular SD {circ_sd_deg(err):.1f}°")
    return 0


def cmd_benchmark(args):
    from .bench.phase_benchmark import run

    s = run(subjects=range(1, args.subjects + 1), out=args.out)
    print(f"done: {s['n_subjects']} subjects in {s['seconds']} s -> {args.out}/benchmark.json")
    return 0


def cmd_screenshots(args):
    from .gui.app import render_screenshots

    for p in render_screenshots(args.out):
        print(p)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="neuroback", description="Closed-loop alpha-phase-locked visual stimulation.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gui", help="desktop app")
    g.add_argument("--board", choices=["simulated", "playback", "synthetic", "cyton"], default="simulated")
    g.add_argument("--port", help="Cyton dongle serial port, e.g. /dev/cu.usbserial-XXXX or COM3")
    g.add_argument("--channel", type=int, default=8, help="Cyton input (1-8) with the occipital electrode")
    g.add_argument("--subject", type=int, default=1, help="PhysioNet subject for --board playback")
    g.add_argument("--trigger-port", help="Arduino serial port (omit for an on-screen LED)")
    g.add_argument("--latency-ms", type=float, default=0.0, help="measured output latency to compensate")
    g.add_argument("--estimator", choices=["ecHT", "AR"], default="ecHT")
    g.set_defaults(func=cmd_gui)

    d = sub.add_parser("demo", help="headless closed loop on simulated alpha")
    d.add_argument("--seconds", type=float, default=60)
    d.add_argument("--target", type=float, default=0)
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(func=cmd_demo)

    b = sub.add_parser("benchmark", help="phase-accuracy benchmark on PhysioNet EEG (downloads ~140 MB)")
    b.add_argument("--subjects", type=int, default=109)
    b.add_argument("--out", default="results")
    b.set_defaults(func=cmd_benchmark)

    s = sub.add_parser("screenshots", help="render app screenshots (offscreen)")
    s.add_argument("--out", default="docs/figures")
    s.set_defaults(func=cmd_screenshots)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
