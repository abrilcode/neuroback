"""Colours and Qt stylesheet. Navy + mint carry over from the 2023 NeuroBack app."""

BG = "#0A1820"
PANEL = "#10232C"
PANEL_2 = "#153140"
BORDER = "#21404D"
TEXT = "#E7F1F3"
MUTED = "#8BA6AF"
MINT = "#6AFFA4"  # the 2023 trace colour
FLASH = "#FFD166"
DANGER = "#FF5C61"
BRAND = "#1E3B4D"  # the 2023 window colour

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QFrame#Header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QFrame#Header QLabel {{ background: transparent; }}
QLabel#Footer {{ color: {MUTED}; background: {PANEL}; border-top: 1px solid {BORDER}; padding: 8px 18px; font-size: 11px; }}
QLabel#Brand {{ font-size: 20px; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#Muted, QLabel.muted {{ color: {MUTED}; }}
QLabel#H1 {{ font-size: 22px; font-weight: 600; }}
QLabel#Pill {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 11px; padding: 3px 10px; color: {MUTED}; }}
QFrame#Panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#Tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel#TileValue {{ font-size: 26px; font-weight: 600; background: transparent; }}
QLabel#TileLabel {{ color: {MUTED}; font-size: 11px; background: transparent; text-transform: uppercase; }}
QListWidget#Nav {{ background: {PANEL}; border: none; border-right: 1px solid {BORDER}; padding-top: 8px; outline: 0; }}
QListWidget#Nav::item {{ padding: 11px 18px; color: {MUTED}; border-left: 3px solid transparent; }}
QListWidget#Nav::item:selected {{ color: {TEXT}; background: {PANEL_2}; border-left: 3px solid {MINT}; }}
QListWidget#Nav::item:disabled {{ color: #4C6670; }}
QPushButton {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 14px; }}
QPushButton:hover {{ border-color: {MINT}; }}
QPushButton:disabled {{ color: #4C6670; border-color: {PANEL_2}; }}
QPushButton#Primary {{ background: {MINT}; color: #062014; border: none; font-weight: 600; }}
QPushButton#Primary:disabled {{ background: #2D5A45; color: #8BB8A0; }}
QPushButton#Stop {{ background: {DANGER}; color: white; border: none; font-weight: 700; padding: 8px 18px; }}
QProgressBar {{ background: {PANEL_2}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {MINT}; border-radius: 4px; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 8px; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 14px; background: {PANEL}; }}
QGroupBox QLabel {{ background: transparent; }}
QRadioButton::indicator, QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {MUTED}; background: {PANEL_2}; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {{ background: {MINT}; border-color: {MINT}; }}
QListWidget {{ background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 8px; }}
QListWidget::item {{ padding: 8px; }}
QListWidget::item:selected {{ background: {BRAND}; color: {TEXT}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {MUTED}; }}
QTableWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: {PANEL_2}; color: {MUTED}; border: none; padding: 6px; }}
QSlider::groove:horizontal {{ background: {PANEL_2}; height: 6px; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {MINT}; width: 16px; margin: -6px 0; border-radius: 8px; }}
"""
