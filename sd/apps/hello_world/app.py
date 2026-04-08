# apps/hello_world/app.py
# CyberDeck app: Hello World | portrait 240×320

import displayio
import terminalio
import time
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

_COLORS = [ui.C_GREEN_HI, ui.C_AMBER, ui.C_WHITE, ui.C_RED, ui.C_GREEN_GLOW, ui.C_GREEN_MID]


def run(display, touch, W, H):
    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:HELLO WORLD", "v1.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # ── Decorative border box ─────────────────────────────────────────────────
    bx, by, bw, bh = 10, 65, W - 20, 140
    ui.make_border(scene, bx,     by,     bw,     bh,     ui.C_GREEN_MID)
    ui.make_border(scene, bx + 2, by + 2, bw - 4, bh - 4, ui.C_GREEN_DIM)
    for cx, cy in [(bx, by), (bx + bw - 8, by),
                   (bx, by + bh - 8), (bx + bw - 8, by + bh - 8)]:
        ui.solid_rect(scene, cx, cy, 8, 8, ui.C_GREEN_MID)

    # ── Greeting ──────────────────────────────────────────────────────────────
    greet_lbl = label.Label(terminalio.FONT, text="HELLO,", color=ui.C_GREEN_HI, scale=2)
    greet_lbl.anchor_point = (0.5, 0.5)
    greet_lbl.anchored_position = (W // 2, 98)
    scene.append(greet_lbl)

    oper_lbl = label.Label(terminalio.FONT, text="OPERATOR", color=ui.C_GREEN_HI, scale=2)
    oper_lbl.anchor_point = (0.5, 0.5)
    oper_lbl.anchored_position = (W // 2, 136)
    scene.append(oper_lbl)

    # ── Status rows ───────────────────────────────────────────────────────────
    sys_lbl = label.Label(terminalio.FONT, text="[ SYSTEM NOMINAL ]",
                          color=ui.C_GREEN_DIM, scale=1)
    sys_lbl.anchor_point = (0.5, 0.5)
    sys_lbl.anchored_position = (W // 2, 240)
    scene.append(sys_lbl)

    tap_lbl = label.Label(terminalio.FONT, text="TAPS: 0", color=ui.C_AMBER, scale=1)
    tap_lbl.anchor_point = (0.5, 0.5)
    tap_lbl.anchored_position = (W // 2, 260)
    scene.append(tap_lbl)

    ui.make_footer(scene, "TAP SCREEN  ^ SWIPE UP to quit")
    display.root_group = scene

    color_idx = 0
    tap_count = 0
    finger_down = False
    sx = sy = lx = ly = 0

    while True:
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
            tap_count += 1
            color_idx = (color_idx + 1) % len(_COLORS)
            col = _COLORS[color_idx]
            greet_lbl.color = col
            oper_lbl.color  = col
            tap_lbl.text = "TAPS: " + str(tap_count)

    display.root_group = displayio.Group()
