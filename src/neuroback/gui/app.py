"""NeuroBack desktop app (PyQt6).

Step flow: Participant -> Calibrate -> Phase sweep -> Stimulate -> Results.
Runs without hardware on simulated alpha or a recording; with an OpenBCI Cyton and the
Arduino trigger it drives a real LED.
"""

from __future__ import annotations

import math
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..analysis import circ_mean_deg, phase_at, phase_dependence_test, plv, wrap
from ..closedloop import ClosedLoop, OpenLoop, RandomPhase
from ..dsp import band_power, individual_alpha_frequency, offline_phase, welch_psd
from ..phase import ARForecast, EcHT
from ..protocol import SweepConfig
from ..safety import SCREENING_QUESTIONS, WARNING, Screening
from ..sources import EEGSource, SimulatedAlpha
from ..stimulators import Stimulator, TriggerScheduler, VirtualStimulator
from ..storage import Store
from . import theme
from .widgets import LedIndicator, PhaseDial, Tile

TICK_MS = 20
DISPLAY_S = 5.0
pg.setConfigOptions(antialias=True, background=theme.PANEL, foreground=theme.MUTED)


def _panel() -> QFrame:
    f = QFrame()
    f.setObjectName("Panel")
    return f


def _h1(text: str, sub: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 6)
    t = QLabel(text)
    t.setObjectName("H1")
    lay.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setObjectName("Muted")
        s.setWordWrap(True)
        lay.addWidget(s)
    return w


class MainWindow(QMainWindow):
    def __init__(self, source: EEGSource, stimulator: Stimulator | None = None, data_dir: str = "neuroback-data",
                 latency_ms: float = 0.0, estimator: str = "ecHT"):
        super().__init__()
        self.setWindowTitle(f"NeuroBack {__version__}")
        self.resize(1280, 800)
        self.source = source
        self.fs = source.fs
        self.virtual = not getattr(source, "realtime", True)
        self.store = Store(data_dir)
        self.pid: str | None = None
        self.iaf: float | None = None
        self.amp_gate: float | None = None
        self.latency_s = latency_ms / 1000
        self.estimator_name = estimator
        self.display = deque(maxlen=int(DISPLAY_S * self.fs))
        self.history = deque(maxlen=int(30 * self.fs))  # for online accuracy
        self.n_total = 0
        self.flash_times: deque[float] = deque(maxlen=400)  # sample-clock seconds
        self.engine = None
        self.mode = "idle"  # idle | calibrate | sweep | stimulate
        self.recording: list[np.ndarray] = []
        self.events: list[dict] = []
        self.sweep_rows: list[dict] = []

        self.led = LedIndicator()
        self.stim = stimulator or VirtualStimulator()
        if isinstance(self.stim, VirtualStimulator) and not self.virtual:
            self.stim.on_flash = self.led.flash
        self.sched = None if self.virtual else TriggerScheduler(self.stim)

        self._build()
        QShortcut(QKeySequence("Esc"), self, activated=self.emergency_stop)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.source.start()
        self.wall0 = time.perf_counter()
        if not self.virtual:
            self.timer.start(TICK_MS)

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 10, 18, 10)
        brand = QLabel("NeuroBack")
        brand.setObjectName("Brand")
        hl.addWidget(brand)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("Muted")
        hl.addWidget(ver)
        hl.addSpacing(16)
        self.src_pill = QLabel(self.source.label)
        self.src_pill.setObjectName("Pill")
        hl.addWidget(self.src_pill)
        self.pid_pill = QLabel("No participant")
        self.pid_pill.setObjectName("Pill")
        hl.addWidget(self.pid_pill)
        self.iaf_pill = QLabel("IAF –")
        self.iaf_pill.setObjectName("Pill")
        hl.addWidget(self.iaf_pill)
        hl.addStretch(1)
        hl.addWidget(QLabel("LED"))
        hl.addWidget(self.led)
        stop = QPushButton("STOP  (Esc)")
        stop.setObjectName("Stop")
        stop.clicked.connect(self.emergency_stop)
        hl.addWidget(stop)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(210)
        for i, name in enumerate(["1  Participant", "2  Calibrate", "3  Phase sweep", "4  Stimulate", "5  Results"]):
            QListWidgetItem(name, self.nav)
        self.pages = QStackedWidget()
        for page in (self._page_participant(), self._page_calibrate(), self._page_sweep(), self._page_stimulate(), self._page_results()):
            wrap_w = QWidget()
            wl = QVBoxLayout(wrap_w)
            wl.setContentsMargins(28, 22, 28, 22)
            wl.addWidget(page)
            self.pages.addWidget(wrap_w)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)

        foot = QLabel("⚠  " + WARNING)
        foot.setWordWrap(True)
        foot.setObjectName("Footer")
        outer.addWidget(foot)
        self.setCentralWidget(root)
        self._update_gates()

    def _eeg_plot(self) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setMenuEnabled(False)
        pw.showGrid(x=False, y=True, alpha=0.15)
        pw.setLabel("bottom", "time (s)")
        pw.setLabel("left", "µV")
        pw.setMouseEnabled(False, False)
        return pw

    def _page_participant(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_h1("Participant", "Participants exist only as random pseudonyms. Names are never stored. "
                                          "Stimulation unlocks after photosensitivity screening and consent."))
        row = QHBoxLayout()
        form = QGroupBox("New participant")
        fl = QVBoxLayout(form)
        self.age = QComboBox()
        self.age.addItems(["18-29", "30-44", "45-64", "65+"])
        fl.addWidget(QLabel("Age band"))
        fl.addWidget(self.age)
        fl.addSpacing(8)
        hdr = QLabel("Photosensitivity screening (any “yes” locks stimulation)")
        hdr.setObjectName("Muted")
        fl.addWidget(hdr)
        self.answers: list[QButtonGroup] = []
        for q in SCREENING_QUESTIONS:
            ql = QHBoxLayout()
            lab = QLabel(q)
            lab.setWordWrap(True)
            ql.addWidget(lab, 1)
            grp = QButtonGroup(form)
            for txt in ("No", "Yes"):
                rb = QRadioButton(txt)
                grp.addButton(rb)
                ql.addWidget(rb)
            self.answers.append(grp)
            fl.addLayout(ql)
        self.consent = QCheckBox("Participant gave informed consent and read the flashing-light warning")
        fl.addWidget(self.consent)
        add = QPushButton("Create participant")
        add.setObjectName("Primary")
        add.clicked.connect(self.create_participant)
        fl.addSpacing(6)
        fl.addWidget(add)
        fl.addStretch(1)
        row.addWidget(form, 3)
        right = QGroupBox("Participants")
        rl = QVBoxLayout(right)
        self.plist = QListWidget()
        self.plist.itemClicked.connect(lambda it: self.select_participant(it.data(Qt.ItemDataRole.UserRole)))
        rl.addWidget(self.plist)
        erase = QPushButton("Delete participant and data")
        erase.clicked.connect(self.delete_participant)
        rl.addWidget(erase)
        row.addWidget(right, 2)
        lay.addLayout(row)
        self._refresh_participants()
        return w

    def _page_calibrate(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_h1("Calibrate", "Record eyes open, then eyes closed. NeuroBack finds the individual alpha "
                                        "frequency (IAF) after removing the 1/f background, and checks that alpha "
                                        "rises when the eyes close."))
        self.cal_plot = self._eeg_plot()
        self.cal_raw = self.cal_plot.plot(pen=pg.mkPen(theme.MUTED, width=1))
        self.cal_alpha = self.cal_plot.plot(pen=pg.mkPen(theme.MINT, width=2))
        lay.addWidget(self.cal_plot, 3)
        ctl = QHBoxLayout()
        self.btn_eo = QPushButton("Eyes open · 60 s")
        self.btn_ec = QPushButton("Eyes closed · 60 s")
        self.btn_eo.clicked.connect(lambda: self.start_calibration(False))
        self.btn_ec.clicked.connect(lambda: self.start_calibration(True))
        ctl.addWidget(self.btn_eo)
        ctl.addWidget(self.btn_ec)
        self.cal_progress = QProgressBar()
        ctl.addWidget(self.cal_progress, 1)
        lay.addLayout(ctl)
        tiles = QHBoxLayout()
        self.t_iaf, self.t_snr, self.t_react = Tile("Individual alpha frequency"), Tile("Alpha peak above 1/f"), Tile("Eyes-closed / open alpha")
        for t in (self.t_iaf, self.t_snr, self.t_react):
            tiles.addWidget(t)
        self.spec_plot = pg.PlotWidget()
        self.spec_plot.setLabel("bottom", "Hz")
        self.spec_plot.setLabel("left", "log power")
        self.spec_plot.setMouseEnabled(False, False)
        self.spec_plot.setFixedHeight(170)
        tiles.addWidget(self.spec_plot, 2)
        lay.addLayout(tiles, 2)
        self.cal_data = {}
        return w

    def _page_sweep(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_h1("Phase sweep", "Four target phases plus two controls with the same flash rate (open-loop "
                                          "flicker at the IAF, random phase), each repeated in random order. Alpha is "
                                          "measured in the stimulus-free gap after every block, where there is no "
                                          "steady-state visual response."))
        top = QHBoxLayout()
        self.sweep_plot = self._eeg_plot()
        self.sweep_raw = self.sweep_plot.plot(pen=pg.mkPen(theme.MUTED, width=1))
        self.sweep_alpha = self.sweep_plot.plot(pen=pg.mkPen(theme.MINT, width=2))
        self.sweep_flash = pg.ScatterPlotItem(size=9, brush=pg.mkBrush(theme.FLASH), pen=None)
        self.sweep_plot.addItem(self.sweep_flash)
        top.addWidget(self.sweep_plot, 3)
        self.sweep_dial = PhaseDial()
        top.addWidget(self.sweep_dial, 2)
        lay.addLayout(top, 3)
        ctl = QHBoxLayout()
        self.demo_timing = QCheckBox("Demo timing (4 s on / 2 s off, 2 repeats)")
        ctl.addWidget(self.demo_timing)
        self.btn_sweep = QPushButton("Start sweep")
        self.btn_sweep.setObjectName("Primary")
        self.btn_sweep.clicked.connect(self.start_sweep)
        ctl.addWidget(self.btn_sweep)
        self.sweep_status = QLabel("")
        self.sweep_status.setObjectName("Muted")
        ctl.addWidget(self.sweep_status, 1)
        self.sweep_progress = QProgressBar()
        ctl.addWidget(self.sweep_progress, 1)
        lay.addLayout(ctl)
        return w

    def _page_stimulate(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_h1("Stimulate", "Choose a target phase. The loop estimates alpha phase with the "
                                        "endpoint-corrected Hilbert transform and schedules one flash per cycle. "
                                        "Dots show where recent flashes actually landed, measured one second later."))
        top = QHBoxLayout()
        self.stim_plot = self._eeg_plot()
        self.stim_raw = self.stim_plot.plot(pen=pg.mkPen(theme.MUTED, width=1))
        self.stim_alpha = self.stim_plot.plot(pen=pg.mkPen(theme.MINT, width=2))
        self.stim_flash = pg.ScatterPlotItem(size=10, brush=pg.mkBrush(theme.FLASH), pen=None)
        self.stim_plot.addItem(self.stim_flash)
        top.addWidget(self.stim_plot, 3)
        side = QVBoxLayout()
        self.stim_dial = PhaseDial()
        side.addWidget(self.stim_dial, 1)
        sl = QHBoxLayout()
        sl.addWidget(QLabel("Target"))
        self.target = QSlider(Qt.Orientation.Horizontal)
        self.target.setRange(0, 359)
        self.target.valueChanged.connect(self._target_changed)
        sl.addWidget(self.target, 1)
        self.target_lab = QLabel("0°")
        sl.addWidget(self.target_lab)
        side.addLayout(sl)
        top.addLayout(side, 2)
        lay.addLayout(top, 3)
        tiles = QHBoxLayout()
        self.t_rate, self.t_plv, self.t_err, self.t_amp = Tile("Flashes / s"), Tile("Phase locking (PLV)"), Tile("Mean phase error"), Tile("Alpha amplitude")
        for t in (self.t_rate, self.t_plv, self.t_err, self.t_amp):
            tiles.addWidget(t)
        lay.addLayout(tiles)
        ctl = QHBoxLayout()
        self.btn_stim = QPushButton("Start stimulation")
        self.btn_stim.setObjectName("Primary")
        self.btn_stim.clicked.connect(self.toggle_stimulation)
        ctl.addWidget(self.btn_stim)
        ctl.addStretch(1)
        lay.addLayout(ctl)
        return w

    def _page_results(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(_h1("Results", "Alpha power after each sweep block by condition, with a permutation test "
                                      "for a one-cycle (cosine) dependence on stimulation phase."))
        self.res_plot = pg.PlotWidget()
        self.res_plot.setLabel("left", "post-block alpha power (relative)")
        self.res_plot.setMouseEnabled(False, False)
        lay.addWidget(self.res_plot, 3)
        self.res_text = QLabel("Run a phase sweep to see results.")
        self.res_text.setObjectName("Muted")
        self.res_text.setWordWrap(True)
        lay.addWidget(self.res_text)
        save = QPushButton("Save session")
        save.clicked.connect(self.save_session)
        lay.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        return w

    # ------------------------------------------------------------------ participants
    def _refresh_participants(self):
        self.plist.clear()
        for pid, age, ok in self.store.participants():
            it = QListWidgetItem(f"{pid}   {age or ''}   {'screened ✓' if ok else 'not cleared'}")
            it.setData(Qt.ItemDataRole.UserRole, pid)
            self.plist.addItem(it)

    def create_participant(self):
        ans = []
        for grp in self.answers:
            b = grp.checkedButton()
            if b is None:
                QMessageBox.warning(self, "Screening", "Answer every screening question.")
                return
            ans.append(b.text() == "Yes")
        scr = Screening(tuple(ans), self.consent.isChecked())
        pid = self.store.add_participant(self.age.currentText(), scr.passed, self.consent.isChecked())
        self._refresh_participants()
        self.select_participant(pid)
        if not scr.passed:
            QMessageBox.information(self, "Not cleared", f"{pid} was created but is not cleared for flashing-light stimulation.")

    def select_participant(self, pid: str):
        self.pid = pid
        self.pid_pill.setText(pid + ("" if self.store.can_stimulate(pid) else " · not cleared"))
        self._update_gates()

    def delete_participant(self):
        it = self.plist.currentItem()
        if not it:
            return
        pid = it.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete", f"Delete {pid} and all their data?") == QMessageBox.StandardButton.Yes:
            self.store.delete_participant(pid)
            if self.pid == pid:
                self.pid = None
                self.pid_pill.setText("No participant")
            self._refresh_participants()
            self._update_gates()

    def _update_gates(self):
        cleared = bool(self.pid and self.store.can_stimulate(self.pid))
        ready = cleared and self.iaf is not None
        for row, enabled in ((1, bool(self.pid)), (2, ready), (3, ready), (4, True)):
            it = self.nav.item(row)
            flags = it.flags()
            it.setFlags(flags | Qt.ItemFlag.ItemIsEnabled if enabled else flags & ~Qt.ItemFlag.ItemIsEnabled)
        if hasattr(self, "btn_sweep"):
            self.btn_sweep.setEnabled(ready)
            self.btn_stim.setEnabled(ready)

    # ------------------------------------------------------------------ actions
    def start_calibration(self, eyes_closed: bool):
        if hasattr(self.source, "eyes_closed"):
            self.source.eyes_closed = eyes_closed
        self.cal_key = "ec" if eyes_closed else "eo"
        self.cal_buf: list[np.ndarray] = []
        self.cal_needed = int(60 * self.fs)
        self.mode = "calibrate"

    def _finish_calibration(self):
        x = np.concatenate(self.cal_buf)[: self.cal_needed]
        self.cal_data[self.cal_key] = x
        self.mode = "idle"
        self.events.append({"t": self.n_total / self.fs, "event": f"calibration_{self.cal_key}"})
        if "ec" in self.cal_data:
            ec = self.cal_data["ec"]
            peak = individual_alpha_frequency(ec, self.fs)
            self.iaf = peak.freq
            self.t_iaf.set(f"{peak.freq:.2f} Hz")
            self.t_snr.set(f"{peak.snr_db:.1f} dB")
            self.iaf_pill.setText(f"IAF {peak.freq:.2f} Hz")
            _, amp, _ = offline_phase(ec, self.fs, self.iaf)
            self.amp_gate = float(np.quantile(amp, 0.25))
            f, p = welch_psd(ec, self.fs)
            m = (f > 2) & (f < 30)
            self.spec_plot.clear()
            self.spec_plot.plot(f[m], np.log10(p[m]), pen=pg.mkPen(theme.MINT, width=2))
            if "eo" in self.cal_data:
                eo = self.cal_data["eo"]
                p_eo = welch_psd(eo, self.fs)[1]
                self.spec_plot.plot(f[m], np.log10(p_eo[m]), pen=pg.mkPen(theme.MUTED, width=1))
                ratio = band_power(ec, self.fs, (self.iaf - 2, self.iaf + 2)) / max(1e-12, band_power(eo, self.fs, (self.iaf - 2, self.iaf + 2)))
                self.t_react.set(f"× {ratio:.1f}")
            self.spec_plot.addLine(x=self.iaf, pen=pg.mkPen(theme.FLASH, style=Qt.PenStyle.DashLine))
            self._update_gates()

    def _make_engine(self, target_deg: float = 0.0):
        est = EcHT(self.fs, self.iaf) if self.estimator_name == "ecHT" else ARForecast(self.fs, self.iaf)
        loop = ClosedLoop(self.fs, est, f0=self.iaf, target_deg=target_deg, latency_s=self.latency_s,
                          commit_s=TICK_MS / 1000 * 1.25, amp_threshold=self.amp_gate)
        loop.buf[:] = np.asarray(self.history)[-len(loop.buf):] if len(self.history) >= len(loop.buf) else 0
        loop.n_seen = self.n_total
        return loop

    def _offset(self, eng):
        eng.n_seen = self.n_total
        return eng

    def start_sweep(self):
        if not self._can_stimulate():
            return
        cfg = SweepConfig(repeats=2, on_s=4, off_s=2) if self.demo_timing.isChecked() else SweepConfig()
        self.sweep_cfg = cfg
        self.sweep_blocks = cfg.schedule()
        self.sweep_rows = []
        self.flash_times.clear()
        self.block_i = -1
        self.mode = "sweep"
        self._next_block()

    def _next_block(self):
        self.block_i += 1
        if self.block_i >= len(self.sweep_blocks):
            self.mode = "idle"
            self.engine = None
            self._cancel_pending()
            self.sweep_status.setText("Sweep finished")
            self._show_results()
            return
        cond = self.sweep_blocks[self.block_i]
        self.block_cond = cond
        self.block_phase = "on"
        self.block_start = self.n_total
        self.block_samples: list[np.ndarray] = []
        if cond.kind == "phase":
            self.engine = self._make_engine(cond.target_deg)
            self.sweep_dial.set_state(target_deg=cond.target_deg, hits_deg=[])
        elif cond.kind == "open-loop":
            self.engine = self._offset(OpenLoop(self.fs, self.iaf))
        else:
            self.engine = self._offset(RandomPhase(self.fs, self.iaf))
        self.events.append({"t": self.n_total / self.fs, "event": "block_on", "condition": cond.label})
        self.sweep_status.setText(f"Block {self.block_i + 1}/{len(self.sweep_blocks)} · {cond.label}")
        self.sweep_progress.setValue(int(100 * self.block_i / len(self.sweep_blocks)))

    def _sweep_step(self, chunk):
        cfg = self.sweep_cfg
        self.block_samples.append(chunk)
        elapsed = (self.n_total - self.block_start) / self.fs
        if self.block_phase == "on" and elapsed >= cfg.on_s:
            on = np.concatenate(self.block_samples)
            self.block_on_power = band_power(on[int(self.fs):], self.fs, (self.iaf - 2, self.iaf + 2))
            self.block_phase = "off"
            self.engine = None
            self._cancel_pending()
            self.block_samples = []
            self.block_start = self.n_total
            self.events.append({"t": self.n_total / self.fs, "event": "block_off"})
        elif self.block_phase == "off" and elapsed >= cfg.off_s:
            off = np.concatenate(self.block_samples)
            p_off = band_power(off[int(0.5 * self.fs):], self.fs, (self.iaf - 2, self.iaf + 2))
            c = self.block_cond
            self.sweep_rows.append({"condition": c.label, "kind": c.kind, "target_deg": c.target_deg,
                                    "alpha_on": self.block_on_power, "alpha_off": p_off})
            self._next_block()

    def toggle_stimulation(self):
        if self.mode == "stimulate":
            self.mode = "idle"
            self.engine = None
            self._cancel_pending()
            self.btn_stim.setText("Start stimulation")
            self.events.append({"t": self.n_total / self.fs, "event": "stim_stop"})
            return
        if not self._can_stimulate():
            return
        self.engine = self._make_engine(self.target.value())
        self.mode = "stimulate"
        self.stim_t0 = self.n_total / self.fs
        self.btn_stim.setText("Stop stimulation")
        self.events.append({"t": self.n_total / self.fs, "event": "stim_start", "target_deg": self.target.value()})

    def _can_stimulate(self) -> bool:
        if not (self.pid and self.store.can_stimulate(self.pid)):
            QMessageBox.warning(self, "Locked", "Select a participant who passed screening and gave consent.")
            return False
        if self.iaf is None:
            QMessageBox.warning(self, "Calibrate first", "Record eyes closed to find the IAF.")
            return False
        return True

    def _target_changed(self, v):
        self.target_lab.setText(f"{v}°")
        self.stim_dial.set_state(target_deg=v)
        if self.mode == "stimulate" and isinstance(self.engine, ClosedLoop):
            self.engine.set_target(v)
            self._cancel_pending()

    def _cancel_pending(self):
        if self.sched:
            self.sched.cancel()

    def emergency_stop(self):
        self.mode = "idle"
        self.engine = None
        self._cancel_pending()
        if hasattr(self, "btn_stim"):
            self.btn_stim.setText("Start stimulation")
        self.events.append({"t": self.n_total / self.fs, "event": "EMERGENCY_STOP"})

    # ------------------------------------------------------------------ loop
    def tick(self, n: int | None = None):
        chunk = self.source.read(n) if self.virtual else self.source.read()
        if len(chunk) == 0:
            return
        self.display.extend(chunk)
        self.history.extend(chunk)
        self.n_total += len(chunk)
        if self.mode in ("sweep", "stimulate"):
            self.recording.append(chunk)

        if self.engine is not None:
            fired = self.engine.push(chunk)
            for t in fired:
                self._on_fired(t)
            pending = getattr(self.engine, "pending", None)
            if self.sched and pending is not None:
                self.sched.tentative(self.wall0 + pending)

        if self.mode == "calibrate":
            self.cal_buf.append(chunk)
            got = sum(len(c) for c in self.cal_buf)
            self.cal_progress.setValue(int(100 * got / self.cal_needed))
            if got >= self.cal_needed:
                self._finish_calibration()
        elif self.mode == "sweep":
            self._sweep_step(chunk)

        self._redraw()

    def _on_fired(self, t: float):
        self.flash_times.append(t)
        self.events.append({"t": round(t, 4), "event": "flash"})
        if self.sched:
            self.sched.commit(self.wall0 + t)
        else:
            self.led.flash()

    def _redraw(self):
        y = np.fromiter(self.display, float)
        if len(y) < 10:
            return
        t_end = self.n_total / self.fs
        t = t_end - (len(y) - 1 - np.arange(len(y))) / self.fs
        page = self.pages.currentIndex()
        flashes = np.array([f for f in self.flash_times if f > t[0]])
        if page == 1:
            self.cal_raw.setData(t, y)
            if self.iaf:
                _, _, a = offline_phase(y, self.fs, self.iaf)
                self.cal_alpha.setData(t, a)
        elif page == 2:
            self.sweep_raw.setData(t, y)
            a = y
            if self.iaf:
                _, _, a = offline_phase(y, self.fs, self.iaf)
                self.sweep_alpha.setData(t, a)
            self.sweep_flash.setData(flashes, np.interp(flashes, t, a) if len(flashes) else [])
            self._update_dial(self.sweep_dial)
        elif page == 3:
            self.stim_raw.setData(t, y)
            a = y
            if self.iaf:
                _, _, a = offline_phase(y, self.fs, self.iaf)
                self.stim_alpha.setData(t, a)
            self.stim_flash.setData(flashes, np.interp(flashes, t, a) if len(flashes) else [])
            self._update_dial(self.stim_dial)
            self._update_accuracy()

    def _update_dial(self, dial: PhaseDial):
        if isinstance(self.engine, ClosedLoop) and self.iaf and len(self.history) >= self.engine.est.window:
            e = self.engine.est.estimate(np.fromiter(self.history, float)[-self.engine.est.window:])
            dial.set_state(phase_deg=math.degrees(e.phase) % 360)

    def _update_accuracy(self):
        """Measure where recent flashes landed, using the non-causal phase 1 s after the fact."""
        if not self.iaf or len(self.history) < 6 * self.fs:
            return
        h = np.fromiter(self.history, float)[-int(8 * self.fs):]
        t0 = self.n_total / self.fs - len(h) / self.fs
        truth, amp, _ = offline_phase(h, self.fs, self.iaf)
        f = np.array([x for x in self.flash_times if t0 + 1 < x < self.n_total / self.fs - 1])
        if self.mode == "stimulate":
            f = f[f > self.stim_t0]
        if len(f) < 5:
            return
        ph = phase_at(f - t0, truth, self.fs)
        err = wrap(ph - math.radians(self.target.value()))
        self.stim_dial.set_state(hits_deg=np.degrees(ph) % 360)
        self.t_plv.set(f"{plv(err):.2f}")
        self.t_err.set(f"{circ_mean_deg(err):+.0f}°")
        self.t_rate.set(f"{len(f) / (f[-1] - f[0] + 1e-9):.1f}")
        self.t_amp.set(f"{np.median(amp):.1f} µV")

    def _show_results(self):
        rows = self.sweep_rows
        if not rows:
            return
        base = np.mean([r["alpha_off"] for r in rows]) or 1.0
        labels = []
        means, errs = [], []
        for cond in self.sweep_cfg.conditions():
            vals = np.array([r["alpha_off"] / base for r in rows if r["condition"] == cond.label])
            labels.append(cond.label)
            means.append(vals.mean())
            errs.append(vals.std(ddof=1) / np.sqrt(len(vals)) if len(vals) > 1 else 0)
        x = np.arange(len(labels))
        self.res_plot.clear()
        colors = [theme.MINT] * len(self.sweep_cfg.phases_deg) + [theme.MUTED] * (len(labels) - len(self.sweep_cfg.phases_deg))
        self.res_plot.addItem(pg.BarGraphItem(x=x, height=means, width=0.6, brushes=[pg.mkBrush(c) for c in colors]))
        self.res_plot.addItem(pg.ErrorBarItem(x=x, y=np.array(means), height=2 * np.array(errs), beam=0.2, pen=pg.mkPen(theme.TEXT)))
        self.res_plot.getAxis("bottom").setTicks([list(zip(x, labels))])
        ph_rows = [r for r in rows if r["kind"] == "phase"]
        test = phase_dependence_test(np.radians([r["target_deg"] for r in ph_rows]), [r["alpha_off"] for r in ph_rows], n_perm=2000)
        self.res_text.setText(
            f"{len(rows)} blocks. Cosine fit across target phases: amplitude {test['amplitude']:.3g}, preferred phase "
            f"{test['preferred_deg']:.0f}°, permutation p = {test['p']:.3f}. A single session is a pilot; "
            "confirm any preferred phase on new blocks before using it."
            + (" Simulated EEG does not respond to light, so no phase effect is expected here."
               if isinstance(self.source, SimulatedAlpha) else ""))
        self.nav.setCurrentRow(4)

    def save_session(self):
        if not self.pid or not self.recording:
            QMessageBox.information(self, "Nothing to save", "Run a sweep or stimulation first.")
            return
        sid = self.store.save_session(self.pid, np.concatenate(self.recording), self.fs, self.events, self.iaf,
                                      {"estimator": self.estimator_name, "latency_s": self.latency_s, "sweep": self.sweep_rows})
        QMessageBox.information(self, "Saved", f"Session {sid} saved for {self.pid}.")

    def closeEvent(self, ev):
        self.timer.stop()
        if self.sched:
            self.sched.stop()
        self.source.stop()
        self.stim.close()
        super().closeEvent(ev)


def main(source: EEGSource | None = None, stimulator: Stimulator | None = None, **kw) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    win = MainWindow(source or SimulatedAlpha(), stimulator, **kw)
    win.show()
    return app.exec()


def render_screenshots(out_dir: Path) -> list[Path]:
    """Drive the app on simulated alpha (virtual clock) and save a screenshot of each page."""
    import tempfile

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    src = SimulatedAlpha(realtime=False, iaf=10.2, seed=11)
    win = MainWindow(src, data_dir=tempfile.mkdtemp())
    win.resize(1440, 900)
    win.show()
    step = int(win.fs * TICK_MS / 1000)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    def run(seconds):
        for _ in range(int(seconds * 1000 / TICK_MS)):
            win.tick(step)
        app.processEvents()

    for grp in win.answers:
        grp.buttons()[0].setChecked(True)
    win.consent.setChecked(True)
    win.create_participant()
    win.store.add_participant("30-44", True, True)
    win._refresh_participants()
    app.processEvents()
    paths.append(out_dir / "app-participant.png")
    win.grab().save(str(paths[-1]))

    win.nav.setCurrentRow(1)
    win.start_calibration(False)
    run(61)
    win.start_calibration(True)
    run(61)
    run(4)
    paths.append(out_dir / "app-calibrate.png")
    win.grab().save(str(paths[-1]))

    win.nav.setCurrentRow(3)
    win.target.setValue(0)
    win.toggle_stimulation()
    run(12)
    paths.append(out_dir / "app-stimulate.png")
    win.grab().save(str(paths[-1]))
    win.toggle_stimulation()

    win.nav.setCurrentRow(2)
    win.demo_timing.setChecked(True)
    win.start_sweep()
    run(3.8)
    paths.append(out_dir / "app-sweep.png")
    win.grab().save(str(paths[-1]))
    run(80)
    paths.append(out_dir / "app-results.png")
    win.grab().save(str(paths[-1]))
    win.close()
    return paths
