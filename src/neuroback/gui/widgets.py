"""Custom widgets: phase dial, LED indicator, metric tile."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from . import theme


class PhaseDial(QWidget):
    """Alpha cycle as a clock face: 0° (peak) at the top, 180° (trough) at the bottom.

    Shows the target phase (mint wedge), the live phase estimate (needle) and the measured
    phase of recent stimuli (dots), so you can see the loop locking on.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_deg = 0.0
        self.phase_deg: float | None = None
        self.hits_deg: list[float] = []
        self.setMinimumSize(220, 220)

    def set_state(self, target_deg=None, phase_deg=None, hits_deg=None):
        if target_deg is not None:
            self.target_deg = target_deg
        if phase_deg is not None:
            self.phase_deg = phase_deg
        if hits_deg is not None:
            self.hits_deg = list(hits_deg)[-80:]
        self.update()

    @staticmethod
    def _pt(c: QPointF, r: float, deg: float) -> QPointF:
        a = math.radians(deg)
        return QPointF(c.x() + r * math.sin(a), c.y() - r * math.cos(a))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width() - 120, self.height() - 50)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = side / 2
        p.setPen(QPen(QColor(theme.BORDER), 2))
        p.setBrush(QBrush(QColor(theme.PANEL)))
        p.drawEllipse(c, r, r)
        # target wedge (+-20 deg)
        p.setPen(Qt.PenStyle.NoPen)
        col = QColor(theme.MINT)
        col.setAlpha(60)
        p.setBrush(col)
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        p.drawPie(rect, int((90 - self.target_deg - 20) * 16), int(40 * 16))
        # ticks + labels
        p.setPen(QPen(QColor(theme.MUTED), 1))
        f = QFont()
        f.setPointSize(9)
        p.setFont(f)
        for deg, lab in ((0, "0° peak"), (90, "90°"), (180, "180° trough"), (270, "270°")):
            p.drawLine(self._pt(c, r - 8, deg), self._pt(c, r, deg))
            q = self._pt(c, r + 12, deg)
            p.drawText(QRectF(q.x() - 45, q.y() - 8, 90, 16), Qt.AlignmentFlag.AlignCenter, lab)
        # hits
        hit = QColor(theme.FLASH)
        for i, h in enumerate(self.hits_deg):
            hit.setAlpha(int(70 + 185 * (i + 1) / max(1, len(self.hits_deg))))
            p.setBrush(hit)
            p.drawEllipse(self._pt(c, r * 0.82, h), 4, 4)
        # needle
        if self.phase_deg is not None:
            p.setPen(QPen(QColor(theme.TEXT), 3, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(c, self._pt(c, r * 0.68, self.phase_deg))
        p.setBrush(QColor(theme.MINT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c, 5, 5)
        p.end()


class LedIndicator(QWidget):
    """On-screen copy of the stimulus LED; lights up on each flash and fades."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedSize(46, 46)
        self._t = QTimer(self)
        self._t.timeout.connect(self._decay)
        self._t.start(30)

    def flash(self):
        self.level = 1.0
        self.update()

    def _decay(self):
        if self.level > 0:
            self.level = max(0.0, self.level - 0.25)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        g = QRadialGradient(c, 22)
        on = QColor(theme.FLASH)
        off = QColor(theme.PANEL_2)
        mix = QColor(
            int(off.red() + (on.red() - off.red()) * self.level),
            int(off.green() + (on.green() - off.green()) * self.level),
            int(off.blue() + (on.blue() - off.blue()) * self.level),
        )
        g.setColorAt(0, mix)
        g.setColorAt(1, QColor(theme.BG))
        p.setBrush(g)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawEllipse(c, 20, 20)
        p.end()


class Tile(QFrame):
    def __init__(self, label: str, value: str = "–", parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.value = QLabel(value)
        self.value.setObjectName("TileValue")
        lab = QLabel(label)
        lab.setObjectName("TileLabel")
        lay.addWidget(lab)
        lay.addWidget(self.value)

    def set(self, text: str):
        self.value.setText(text)
