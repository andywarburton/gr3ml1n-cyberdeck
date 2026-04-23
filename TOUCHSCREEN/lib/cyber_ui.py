# cyber_ui.py - Shared cyberpunk UI library for CyberDeck OS
# Waveshare ESP32-S3 Touch LCD 2.8 | PORTRAIT 240×320 | CircuitPython 10.x
#
# Theme system: call set_theme("amber") to switch at runtime.
# The chosen theme is saved to /theme.json and auto-loaded on next boot.

import displayio
import terminalio
import vectorio
import time
import json
from adafruit_display_text import label

# ── Screen dimensions (portrait) ──────────────────────────────────────────────
W = 240
H = 320

# ── Layout zones ───────────────────────────────────────────────────────────────
TITLE_H   = 20
CONTENT_Y = 21
FOOTER_Y  = 300
FOOTER_H  = 20
CONTENT_H = FOOTER_Y - CONTENT_Y   # 279

# ── Gesture thresholds ─────────────────────────────────────────────────────────
SWIPE_EDGE   = 35
SWIPE_MIN    = 30
BTN_Y_MARGIN = 20

# ── Fixed accent colors (never themed — used for system warnings/errors) ───────
C_AMBER     = 0xFF8800
C_AMBER_DIM = 0x664400
C_RED       = 0xFF2200
C_RED_DIM   = 0x220000
C_WHITE     = 0xDDFFDD

# ── Theme definitions ──────────────────────────────────────────────────────────
THEME_NAMES = ["green", "amber", "red", "purple", "grey", "paper", "retrowave"]

THEMES = {
    "green": {
        "bg":        0x000A00,
        "bg_scan":   0x000300,
        "bg_panel":  0x001200,
        "bg_header": 0x001A00,
        "dim":       0x226622,
        "mid":       0x44AA44,
        "primary":   0x00AA00,
        "hi":        0x00FF00,
        "glow":      0x55FF55,
    },
    "amber": {
        "bg":        0x0A0500,
        "bg_scan":   0x030200,
        "bg_panel":  0x150A00,
        "bg_header": 0x1E0F00,
        "dim":       0x886644,
        "mid":       0xAA7744,
        "primary":   0xBB6000,
        "hi":        0xFFCC66,
        "glow":      0xFFAA44,
    },
    "red": {
        "bg":        0x0A0000,
        "bg_scan":   0x030000,
        "bg_panel":  0x160000,
        "bg_header": 0x200000,
        "dim":       0x664444,
        "mid":       0x994444,
        "primary":   0xCC3333,
        "hi":        0xFF5544,
        "glow":      0xFF7766,
    },
    "purple": {
        "bg":        0x0A0010,
        "bg_scan":   0x030008,
        "bg_panel":  0x150025,
        "bg_header": 0x1A0030,
        "dim":       0x8855BB,
        "mid":       0xAA77DD,
        "primary":   0xBB88FF,
        "hi":        0xDDAAFF,
        "glow":      0xEEBBFF,
    },
    "grey": {
        "bg":        0x0A0A0A,
        "bg_scan":   0x040404,
        "bg_panel":  0x141414,
        "bg_header": 0x1E1E1E,
        "dim":       0x666666,
        "mid":       0x888888,
        "primary":   0xAAAAAA,
        "hi":        0xFFFFFF,
        "glow":      0xEEEEEE,
    },
    "paper": {
        "bg":        0xF5F0E6,
        "bg_scan":   0xEBE5D8,
        "bg_panel":  0xE8E0D0,
        "bg_header": 0xDDD5C5,
        "dim":       0x8B7355,
        "mid":       0xA67C52,
        "primary":   0xC65D3B,
        "hi":        0x4A3520,
        "glow":      0xD2691E,
    },
    "retrowave": {
        "bg":        0x08001A,
        "bg_scan":   0x04000D,
        "bg_panel":  0x120030,
        "bg_header": 0x1C0044,
        "dim":       0x8833AA,
        "mid":       0xBB44CC,
        "primary":   0xFF2D78,
        "hi":        0xFF88FF,
        "glow":      0xAADDFF,
    },
}

# ── Theme-able color globals ────────────────────────────────────────────────────
# Initialised to "green"; overwritten by load_theme() at the bottom of this file.
C_BG         = THEMES["green"]["bg"]
C_BG_SCAN    = THEMES["green"]["bg_scan"]
C_BG_PANEL   = THEMES["green"]["bg_panel"]
C_BG_HEADER  = THEMES["green"]["bg_header"]
C_GREEN_DIM  = THEMES["green"]["dim"]
C_GREEN_MID  = THEMES["green"]["mid"]
C_GREEN      = THEMES["green"]["primary"]
C_GREEN_HI   = THEMES["green"]["hi"]
C_GREEN_GLOW = THEMES["green"]["glow"]

_active_theme = "green"
_THEME_FILE   = "/theme.json"


def _apply_theme(name):
    """Update all theme-able globals in-place.  Affects every subsequent call."""
    global _active_theme
    global C_BG, C_BG_SCAN, C_BG_PANEL, C_BG_HEADER
    global C_GREEN_DIM, C_GREEN_MID, C_GREEN, C_GREEN_HI, C_GREEN_GLOW
    t = THEMES.get(name, THEMES["green"])
    _active_theme = name
    C_BG         = t["bg"]
    C_BG_SCAN    = t["bg_scan"]
    C_BG_PANEL   = t["bg_panel"]
    C_BG_HEADER  = t["bg_header"]
    C_GREEN_DIM  = t["dim"]
    C_GREEN_MID  = t["mid"]
    C_GREEN      = t["primary"]
    C_GREEN_HI   = t["hi"]
    C_GREEN_GLOW = t["glow"]


def get_active_theme():
    """Return the name of the currently active theme (e.g. 'amber')."""
    return _active_theme


def set_theme(name):
    """Apply a theme immediately and persist it to /theme.json."""
    if name in THEMES:
        _apply_theme(name)
        _save_theme(name)


def _save_theme(name):
    try:
        with open(_THEME_FILE, "w") as f:
            json.dump({"theme": name}, f)
    except OSError:
        pass   # filesystem read-only (e.g. USB host connected) — change is
               # still applied in memory for this session


def load_theme():
    """Load persisted theme from /theme.json.  Falls back to 'green'."""
    try:
        with open(_THEME_FILE) as f:
            data = json.load(f)
        name = data.get("theme", "green")
        _apply_theme(name if name in THEMES else "green")
    except (OSError, ValueError):
        _apply_theme("green")


# Apply the saved theme the moment this module is first imported
load_theme()


# ── Low-level primitive ────────────────────────────────────────────────────────

def solid_rect(group, x, y, w, h, color):
    """Append a solid-color rectangle to group.  Returns its Palette."""
    pal = displayio.Palette(1)
    pal[0] = color
    group.append(vectorio.Rectangle(pixel_shader=pal, width=w, height=h, x=x, y=y))
    return pal


# ── Standard chrome ────────────────────────────────────────────────────────────

def make_scan_bg(group, y_start=0, height=None):
    """
    CRT scan-line background via 240×2 TileGrid trick.
    Returns (tilegrid, palette) for brightness animation.
    """
    if height is None:
        height = H - y_start
    bmp = displayio.Bitmap(W, 2, 2)
    for x in range(W):
        bmp[x, 0] = 0
        bmp[x, 1] = 1
    pal = displayio.Palette(2)
    pal[0] = C_BG
    pal[1] = C_BG_SCAN
    rows = max(1, (height + 1) // 2)
    tg = displayio.TileGrid(
        bmp, pixel_shader=pal,
        x=0, y=y_start,
        tile_width=W, tile_height=2,
        width=1, height=rows,
    )
    group.append(tg)
    return tg, pal


def make_title_bar(group, title, right="", time_str=None, battery_str=None):
    """20px title bar at y=0 + 1px separator.
    If time_str and/or battery_str are provided they are shown on the far
    right (replacing the static *right* text).  Returns (title_lbl, right_lbl)."""
    solid_rect(group, 0, 0, W, TITLE_H, C_BG_HEADER)
    solid_rect(group, 0, TITLE_H, W, 1, C_GREEN_MID)

    t_lbl = label.Label(terminalio.FONT, text=title, color=C_GREEN_HI, scale=1)
    t_lbl.anchor_point = (0.0, 0.5)
    t_lbl.anchored_position = (4, TITLE_H // 2)
    group.append(t_lbl)

    status_parts = []
    if time_str:
        status_parts.append(time_str)
    if battery_str:
        status_parts.append(battery_str)
    right_text = " | ".join(status_parts) if status_parts else (right if right else " ")

    r_lbl = label.Label(terminalio.FONT, text=right_text, color=C_GREEN_MID, scale=1)
    r_lbl.anchor_point = (1.0, 0.5)
    r_lbl.anchored_position = (W - 4, TITLE_H // 2)
    group.append(r_lbl)

    return t_lbl, r_lbl


def make_footer(group, hint="^ SWIPE UP to quit"):
    """20px footer at y=FOOTER_Y.  Returns hint_lbl."""
    solid_rect(group, 0, FOOTER_Y - 1, W, 1, C_GREEN_DIM)
    solid_rect(group, 0, FOOTER_Y, W, FOOTER_H, C_BG_HEADER)

    h_lbl = label.Label(terminalio.FONT, text=hint, color=C_GREEN_DIM, scale=1)
    h_lbl.anchor_point = (0.5, 0.5)
    h_lbl.anchored_position = (W // 2, FOOTER_Y + FOOTER_H // 2)
    group.append(h_lbl)
    return h_lbl


def make_button(group, x, y, w, h, text, bg_color=None, text_color=None):
    """Filled rect + centered label.  Returns (rect_pal, lbl)."""
    if bg_color is None:
        bg_color = C_BG_PANEL
    if text_color is None:
        text_color = C_GREEN_HI
    pal = solid_rect(group, x, y, w, h, bg_color)
    lbl = label.Label(terminalio.FONT, text=text, color=text_color, scale=1)
    lbl.anchor_point = (0.5, 0.5)
    lbl.anchored_position = (x + w // 2, y + h // 2)
    group.append(lbl)
    return pal, lbl


def make_border(group, x, y, w, h, color=None):
    """1px outline via four thin rectangles."""
    if color is None:
        color = C_GREEN_MID
    solid_rect(group, x,         y,         w, 1, color)
    solid_rect(group, x,         y + h - 1, w, 1, color)
    solid_rect(group, x,         y,         1, h, color)
    solid_rect(group, x + w - 1, y,         1, h, color)


# ── Boot animation ─────────────────────────────────────────────────────────────

def boot_glitch(display, group):
    """~500 ms boot animation using the active theme's colors."""
    solid_rect(group, 0, 0, W, H, 0x000000)
    display.root_group = group
    time.sleep(0.08)

    _, scan_pal = make_scan_bg(group, 0, H)
    for _ in range(4):
        scan_pal[0] = C_GREEN_GLOW
        scan_pal[1] = C_GREEN_MID
        time.sleep(0.04)
        scan_pal[0] = C_BG
        scan_pal[1] = C_BG_SCAN
        time.sleep(0.03)

    full = ">> [GR3ML1N] <<"
    t_lbl = label.Label(terminalio.FONT, text=" ", color=C_GREEN_HI, scale=2)
    t_lbl.anchor_point = (0.5, 0.5)
    t_lbl.anchored_position = (W // 2, H // 2 - 14)
    group.append(t_lbl)

    sub_lbl = label.Label(terminalio.FONT, text="INITIALIZING SYSTEMS...", color=C_GREEN_DIM, scale=1)
    sub_lbl.anchor_point = (0.5, 0.5)
    sub_lbl.anchored_position = (W // 2, H // 2 + 18)
    group.append(sub_lbl)

    for i in range(2, len(full) + 1, 2):
        t_lbl.text = full[:i]
        time.sleep(0.04)

    time.sleep(0.3)
