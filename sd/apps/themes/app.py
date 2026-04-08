# apps/themes/app.py
# CyberDeck app: Theme Selector | portrait 240×320
#
# Each button is rendered in its own theme's colours so the user
# gets a live preview.  Tapping a button applies and persists the theme.
# The launcher will reflect the new theme immediately on return.

import displayio
import vectorio
import terminalio
import time
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

# ── Button layout ──────────────────────────────────────────────────────────────
_BTN_H   = 46
_BTN_GAP = 4
_BTN_X   = 2
_BTN_W   = ui.W - 4   # 236

# Centre the stack vertically in the content area
_STACK_H  = len(ui.THEME_NAMES) * _BTN_H + (len(ui.THEME_NAMES) - 1) * _BTN_GAP
_BTN_Y0   = ui.CONTENT_Y + (ui.CONTENT_H - _STACK_H) // 2   # ≈ 48

# Color swatches: 4 squares (bg_panel, mid, hi, glow) right-aligned
_SW_W     = 15
_SW_H     = 14
_SW_GAP   = 3
_SW_COUNT = 4
_SW_TOTAL = _SW_COUNT * _SW_W + (_SW_COUNT - 1) * _SW_GAP   # 69px
_SW_X0    = ui.W - _BTN_X - _SW_TOTAL - 4                   # right margin

# Active-indicator bar on the left edge of each button
_IND_W    = 4


def run(display, touch, keyboard, W, H):
    active = ui.get_active_theme()

    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:THEMES", "v1.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # ── Status label ──────────────────────────────────────────────────────────
    status_lbl = label.Label(terminalio.FONT,
        text="ACTIVE: " + active.upper(),
        color=ui.C_GREEN_HI, scale=1)
    status_lbl.anchor_point = (0.5, 0.5)
    status_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 12)
    scene.append(status_lbl)

    ui.solid_rect(scene, 4, ui.CONTENT_Y + 21, W - 8, 1, ui.C_GREEN_DIM)

    # ── Theme buttons ─────────────────────────────────────────────────────────
    btn_info = []   # {"name", "y", "ind_pal"}

    for i, name in enumerate(ui.THEME_NAMES):
        t   = ui.THEMES[name]
        by  = _BTN_Y0 + i * (_BTN_H + _BTN_GAP)
        is_active = (name == active)

        # Button background
        ui.solid_rect(scene, _BTN_X, by, _BTN_W, _BTN_H, t["bg_header"])

        # Left indicator bar (glow = active, invisible bg = inactive)
        ind_col = t["glow"] if is_active else t["bg_header"]
        ind_pal = ui.solid_rect(scene, _BTN_X, by, _IND_W, _BTN_H, ind_col)

        # Theme name  (scale=2, this theme's hi color)
        n_lbl = label.Label(terminalio.FONT,
            text=name.upper(), color=t["hi"], scale=2)
        n_lbl.anchor_point = (0.0, 0.5)
        n_lbl.anchored_position = (_BTN_X + _IND_W + 6, by + _BTN_H // 2)
        scene.append(n_lbl)

        # Color swatches: bg_panel → mid → hi → glow (dark to bright)
        swatch_colors = [t["bg_panel"], t["mid"], t["hi"], t["glow"]]
        for j, col in enumerate(swatch_colors):
            sx = _SW_X0 + j * (_SW_W + _SW_GAP)
            sy_sw = by + (_BTN_H - _SW_H) // 2
            ui.solid_rect(scene, sx, sy_sw, _SW_W, _SW_H, col)

        # Thin bottom separator (use this theme's mid color for variety)
        if i < len(ui.THEME_NAMES) - 1:
            ui.solid_rect(scene, _BTN_X + _IND_W + 2, by + _BTN_H,
                          _BTN_W - _IND_W - 2, 1, t["mid"])

        btn_info.append({"name": name, "y": by, "ind_pal": ind_pal})

    ui.make_footer(scene, "ESC or TAP THEME to quit")
    display.root_group = scene

    finger_down = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        x, y, touching = touch.read()
        time.sleep(0.04)

        if touching:
            lx, ly = x, y
            if not finger_down:
                finger_down = True
                sx, sy = x, y
        elif finger_down:
            finger_down = False

            action = classify_gesture(
                sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN,
            )
            if action and action[0] == "SWIPE UP":
                break

            # Tap — check which button was hit
            for btn in btn_info:
                if btn["y"] <= sy <= btn["y"] + _BTN_H:
                    chosen = btn["name"]
                    t_chosen = ui.THEMES[chosen]

                    # Apply + persist
                    ui.set_theme(chosen)

                    # Update indicator bars: glow on chosen, hidden on others
                    for b in btn_info:
                        t_b = ui.THEMES[b["name"]]
                        b["ind_pal"][0] = (t_b["glow"] if b["name"] == chosen
                                          else t_b["bg_header"])

                    # Update status label using the new theme's hi color
                    status_lbl.text  = "ACTIVE: " + chosen.upper() + " [SAVED]"
                    status_lbl.color = ui.C_GREEN_HI   # now the new theme's hi
                    break

    display.root_group = displayio.Group()
