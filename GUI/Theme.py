"""
Theme.py - thèmes Qt disponibles. Thème par défaut : dark_blue (bleu-nuit,
accents bleu vif), dans l'esprit des terminaux DOM professionnels.
D'autres thèmes peuvent être ajoutés au dict THEMES et sélectionnés via
Settings.get("theme").
"""

NAVY_BG        = "#0a1220"
PANEL_BG       = "#0f1a2b"
HEADER_BG      = "#132238"
DOCK_TITLE_BG  = "#0d1c33"
BORDER_BLUE    = "#1c3a5e"
ACCENT_BLUE    = "#2f7dfd"
ACCENT_BLUE_HI = "#5a9dff"
SELECTION_BLUE = "#173a63"
TEXT_PRIMARY   = "#d9e4f2"
TEXT_MUTED     = "#7d93b3"

DARK_BLUE_THEME = f"""
QWidget {{
    background-color: {NAVY_BG};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
}}
QMainWindow {{ background-color: {NAVY_BG}; }}
QMainWindow::separator {{ background: #050a12; width: 2px; height: 2px; }}
QToolBar {{
    background-color: {DOCK_TITLE_BG};
    border-bottom: 1px solid {BORDER_BLUE};
    spacing: 6px;
    padding: 3px;
}}
QDockWidget {{ titlebar-close-icon: none; border: 1px solid {BORDER_BLUE}; }}
QDockWidget::title {{
    background: {DOCK_TITLE_BG};
    color: {ACCENT_BLUE_HI};
    padding: 5px 8px;
    font-weight: 600;
    border-bottom: 2px solid {ACCENT_BLUE};
}}
QTableWidget, QTableView, QListWidget {{
    background-color: {PANEL_BG};
    alternate-background-color: #0c1729;
    gridline-color: {BORDER_BLUE};
    selection-background-color: {SELECTION_BLUE};
    selection-color: {TEXT_PRIMARY};
    border: none;
}}
QHeaderView::section {{
    background-color: {HEADER_BG};
    color: {ACCENT_BLUE_HI};
    padding: 5px;
    border: none;
    border-bottom: 2px solid {ACCENT_BLUE};
    font-weight: 600;
}}
QMenuBar {{ background-color: {DOCK_TITLE_BG}; color: {TEXT_PRIMARY}; border-bottom: 1px solid {BORDER_BLUE}; }}
QMenuBar::item:selected {{ background-color: {SELECTION_BLUE}; color: {ACCENT_BLUE_HI}; }}
QMenu {{ background-color: {HEADER_BG}; border: 1px solid {ACCENT_BLUE}; }}
QMenu::item:selected {{ background-color: {SELECTION_BLUE}; color: {ACCENT_BLUE_HI}; }}
QPushButton {{
    background-color: {HEADER_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_BLUE};
    border-radius: 3px;
    padding: 4px 12px;
}}
QPushButton:hover {{ background-color: {SELECTION_BLUE}; border-color: {ACCENT_BLUE}; color: {ACCENT_BLUE_HI}; }}
QPushButton:pressed {{ background-color: {ACCENT_BLUE}; color: #051020; }}
QPushButton#buyButton {{ background-color: #0d2a4a; border-color: {ACCENT_BLUE}; color: {ACCENT_BLUE_HI}; font-weight: 600; }}
QPushButton#buyButton:hover {{ background-color: {ACCENT_BLUE}; color: #051020; }}
QPushButton#sellButton {{ background-color: #3a1420; border-color: #c62828; color: #ff8a80; font-weight: 600; }}
QPushButton#sellButton:hover {{ background-color: #c62828; color: #ffffff; }}
QPushButton#killSwitchButton {{ background-color: #4a0f0f; border-color: #ff1744; color: #ff8a80; font-weight: 700; }}
QPushButton#killSwitchButton:hover {{ background-color: #ff1744; color: #ffffff; }}
QStatusBar {{ background-color: {DOCK_TITLE_BG}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER_BLUE}; }}
QLabel {{ color: {TEXT_PRIMARY}; }}
QLineEdit, QSpinBox, QComboBox, QDateTimeEdit {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER_BLUE};
    border-radius: 2px;
    padding: 2px 4px;
    selection-background-color: {ACCENT_BLUE};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT_BLUE}; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {NAVY_BG}; border: none; }}
QScrollBar::handle {{ background: {BORDER_BLUE}; border-radius: 4px; }}
QScrollBar::handle:hover {{ background: {ACCENT_BLUE}; }}
"""


# --- Thème "Jigsaw daytradr" (bleu/rouge) ---------------------------------
# Reprend l'ambiance visuelle du DOM Jigsaw daytradr par défaut : fond très
# sombre, bid en bleu vif, ask en rouge, accents jaune/orange pour les
# alertes et histogrammes de volume.
JG_BG          = "#0b0e11"
JG_PANEL_BG    = "#12161b"
JG_HEADER_BG   = "#181d24"
JG_BORDER      = "#2a323c"
JG_BID_BLUE    = "#2f7dfd"
JG_ASK_RED     = "#e53935"
JG_ACCENT      = "#ffb300"
JG_TEXT        = "#e6e9ee"
JG_TEXT_MUTED  = "#8a93a1"

JIGSAW_BLUE_RED_THEME = f"""
QWidget {{
    background-color: {JG_BG};
    color: {JG_TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
}}
QMainWindow {{ background-color: {JG_BG}; }}
QMainWindow::separator {{ background: #000000; width: 2px; height: 2px; }}
QToolBar {{ background-color: {JG_HEADER_BG}; border-bottom: 1px solid {JG_BORDER}; spacing: 6px; padding: 3px; }}
QDockWidget {{ titlebar-close-icon: none; border: 1px solid {JG_BORDER}; }}
QDockWidget::title {{
    background: {JG_HEADER_BG}; color: {JG_ACCENT}; padding: 5px 8px;
    font-weight: 600; border-bottom: 2px solid {JG_BID_BLUE};
}}
QTableWidget, QTableView, QListWidget {{
    background-color: {JG_PANEL_BG};
    alternate-background-color: #0e1216;
    gridline-color: {JG_BORDER};
    selection-background-color: #1c3a5e;
    selection-color: {JG_TEXT};
    border: none;
}}
QHeaderView::section {{
    background-color: {JG_HEADER_BG}; color: {JG_ACCENT}; padding: 5px;
    border: none; border-bottom: 2px solid {JG_BID_BLUE}; font-weight: 600;
}}
QMenuBar {{ background-color: {JG_HEADER_BG}; color: {JG_TEXT}; border-bottom: 1px solid {JG_BORDER}; }}
QMenuBar::item:selected {{ background-color: {JG_BID_BLUE}; color: #051020; }}
QMenu {{ background-color: {JG_HEADER_BG}; border: 1px solid {JG_BID_BLUE}; }}
QMenu::item:selected {{ background-color: {JG_BID_BLUE}; color: #051020; }}
QPushButton {{
    background-color: {JG_HEADER_BG}; color: {JG_TEXT}; border: 1px solid {JG_BORDER};
    border-radius: 3px; padding: 4px 12px;
}}
QPushButton:hover {{ background-color: #1c232c; border-color: {JG_ACCENT}; color: {JG_ACCENT}; }}
QPushButton:pressed {{ background-color: {JG_ACCENT}; color: #051020; }}
QPushButton#buyButton {{ background-color: #0d2a4a; border-color: {JG_BID_BLUE}; color: #8ab4ff; font-weight: 600; }}
QPushButton#buyButton:hover {{ background-color: {JG_BID_BLUE}; color: #051020; }}
QPushButton#sellButton {{ background-color: #3a1420; border-color: {JG_ASK_RED}; color: #ff8a80; font-weight: 600; }}
QPushButton#sellButton:hover {{ background-color: {JG_ASK_RED}; color: #ffffff; }}
QPushButton#killSwitchButton {{ background-color: #4a0f0f; border-color: #ff1744; color: #ff8a80; font-weight: 700; }}
QPushButton#killSwitchButton:hover {{ background-color: #ff1744; color: #ffffff; }}
QStatusBar {{ background-color: {JG_HEADER_BG}; color: {JG_TEXT_MUTED}; border-top: 1px solid {JG_BORDER}; }}
QLabel {{ color: {JG_TEXT}; }}
QLineEdit, QSpinBox, QComboBox, QDateTimeEdit {{
    background-color: {JG_PANEL_BG}; border: 1px solid {JG_BORDER}; border-radius: 2px;
    padding: 2px 4px; selection-background-color: {JG_BID_BLUE};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {JG_ACCENT}; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {JG_BG}; border: none; }}
QScrollBar::handle {{ background: {JG_BORDER}; border-radius: 4px; }}
QScrollBar::handle:hover {{ background: {JG_ACCENT}; }}
"""

# --- Variante "Jigsaw vert/violet" ----------------------------------------
# Alternative populaire chez de nombreux utilisateurs Jigsaw (bid en vert,
# ask en violet), pour ceux qui préfèrent ce combo au bleu/rouge classique.
JG2_BID_GREEN  = "#00c853"
JG2_ASK_PURPLE = "#ab47bc"

JIGSAW_GREEN_PURPLE_THEME = JIGSAW_BLUE_RED_THEME.replace(
    JG_BID_BLUE, JG2_BID_GREEN
).replace(JG_ASK_RED, JG2_ASK_PURPLE)

THEMES = {
    "dark_blue": DARK_BLUE_THEME,
    "jigsaw_blue_red": JIGSAW_BLUE_RED_THEME,
    "jigsaw_green_purple": JIGSAW_GREEN_PURPLE_THEME,
}


def get_theme(name: str) -> str:
    return THEMES.get(name, DARK_BLUE_THEME)
