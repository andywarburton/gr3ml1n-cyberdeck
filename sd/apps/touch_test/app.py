# apps/touch_test/app.py
# CyberDeck app: Touch Test | portrait 240x320

import displayio
import terminalio
import time
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

# ── Layout constants ──────────────────────────────────────────────────────────
_E          = ui.SWIPE_EDGE                    # 35 px edge-zone depth
_TOP_SEP_Y  = ui.CONTENT_Y + _E               # 56  — line below top zone
_INFO_SEP_Y = 163                              # line below info area
_BOT_SEP_Y  = 264                              # line above bottom zone
_BTN_W      = 64
_BTN_H      = 68
_BTN_GAP    = 12
_BTN_Y      = _INFO_SEP_Y + 8                 # 171
_BTN_X0     = (ui.W - (3 * _BTN_W + 2 * _BTN_GAP)) // 2   # 12


def run(display, touch, keyboard, W, H):
    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:TOUCH TEST", "v1.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # ── Top swipe-down zone (y=21..56) ────────────────────────────────────
    ui.solid_rect(scene, 0, ui.CONTENT_Y, W, _E, ui.C_BG_PANEL)
    tl = label.Label(terminalio.FONT, text="^ SWIPE DOWN",
                     color=ui.C_GREEN_DIM, scale=1)
    tl.anchor_point    = (0.5, 0.5)
    tl.anchored_position = (W // 2, ui.CONTENT_Y + _E // 2)
    scene.append(tl)

    ui.solid_rect(scene, 0, _TOP_SEP_Y, W, 1, ui.C_GREEN_DIM)

    # ── Gesture readout (y=57..100) ───────────────────────────────────────
    gest_lbl = label.Label(terminalio.FONT, text="WAITING...",
                           color=ui.C_GREEN_DIM, scale=2)
    gest_lbl.anchor_point    = (0.5, 0.5)
    gest_lbl.anchored_position = (W // 2, 82)
    scene.append(gest_lbl)

    # ── Coordinate rows (y=105..155) ─────────────────────────────────────
    def _row(txt, y):
        l = label.Label(terminalio.FONT, text=txt,
                        color=ui.C_GREEN, scale=1)
        l.anchor_point    = (0.0, 0.5)
        l.anchored_position = (8, y)
        scene.append(l)
        return l

    start_lbl = _row("START:  ---", 112)
    end_lbl   = _row("END:    ---", 127)
    dist_lbl  = _row("DIST:   ---", 142)

    ui.solid_rect(scene, 0, _INFO_SEP_Y, W, 1, ui.C_GREEN_DIM)

    # ── Left / right swipe hints ──────────────────────────────────────────
    mid_y = (_TOP_SEP_Y + _BOT_SEP_Y) // 2   # vertical centre of inner area

    ll = label.Label(terminalio.FONT, text="<",
                     color=ui.C_GREEN_DIM, scale=1)
    ll.anchor_point    = (0.5, 0.5)
    ll.anchored_position = (_E // 2, mid_y)
    scene.append(ll)

    rl = label.Label(terminalio.FONT, text=">",
                     color=ui.C_GREEN_DIM, scale=1)
    rl.anchor_point    = (0.5, 0.5)
    rl.anchored_position = (W - _E // 2, mid_y)
    scene.append(rl)

    # ── Themed buttons ────────────────────────────────────────────────────
    BUTTONS = [
        {"label": "CMD"},
        {"label": "CTRL"},
        {"label": "SYS"},
    ]
    for i, btn in enumerate(BUTTONS):
        bx = _BTN_X0 + i * (_BTN_W + _BTN_GAP)
        pal, _ = ui.make_button(scene, bx, _BTN_Y, _BTN_W, _BTN_H,
                                btn["label"])
        ui.make_border(scene, bx, _BTN_Y, _BTN_W, _BTN_H, ui.C_GREEN_MID)
        btn["pal"] = pal
        btn["x"]   = bx
        btn["y"]   = _BTN_Y

    # ── Bottom swipe-up zone (y=264..300) ─────────────────────────────────
    ui.solid_rect(scene, 0, _BOT_SEP_Y, W, 1, ui.C_GREEN_DIM)
    ui.solid_rect(scene, 0, _BOT_SEP_Y + 1, W,
                  ui.FOOTER_Y - _BOT_SEP_Y - 1, ui.C_BG_PANEL)
    bl = label.Label(terminalio.FONT, text="v SWIPE UP",
                     color=ui.C_GREEN_DIM, scale=1)
    bl.anchor_point    = (0.5, 0.5)
    bl.anchored_position = (W // 2, (_BOT_SEP_Y + ui.FOOTER_Y) // 2)
    scene.append(bl)

    ui.make_footer(scene, "^ SWIPE UP to quit")
    display.root_group = scene

    # ── Status colours (all use current theme) ────────────────────────────
    STATUS_COLORS = {
        "swipe":  ui.C_GREEN_HI,
        "button": ui.C_GREEN_GLOW,
        "tap":    ui.C_GREEN_MID,
    }

    btn_restore_at  = 0
    btn_restore_idx = -1
    finger_down     = False
    fsx = fsy = flx = fly = 0

    while True:
        now = time.monotonic()

        # Restore flashed button
        if btn_restore_at and now >= btn_restore_at:
            BUTTONS[btn_restore_idx]["pal"][0] = ui.C_BG_PANEL
            btn_restore_at  = 0
            btn_restore_idx = -1

        x, y, touching = touch.read()
        time.sleep(0.04)

        if touching:
            flx, fly = x, y
            if not finger_down:
                finger_down = True
                fsx, fsy = x, y
        elif finger_down:
            finger_down = False
            action = classify_gesture(
                fsx, fsy, flx, fly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN,
                buttons=BUTTONS, btn_y=_BTN_Y, btn_h=_BTN_H, btn_w=_BTN_W,
                btn_y_margin=ui.BTN_Y_MARGIN,
            )
            if not action:
                continue
            if action[0] == "SWIPE UP":
                break

            dx   = flx - fsx
            dy   = fly - fsy
            dist = int((dx * dx + dy * dy) ** 0.5)
            start_lbl.text = "START:  ({},{})".format(fsx, fsy)
            end_lbl.text   = "END:    ({},{})".format(flx, fly)
            dist_lbl.text  = "DIST:   {} px".format(dist)

            if len(action) == 3:
                text, kind, btn_idx = action
                gest_lbl.text  = text[:12]
                gest_lbl.color = STATUS_COLORS.get(kind, ui.C_WHITE)
                BUTTONS[btn_idx]["pal"][0] = ui.C_GREEN_MID
                btn_restore_at  = now + 0.3
                btn_restore_idx = btn_idx
            else:
                text, kind = action
                gest_lbl.text  = text[:12]
                gest_lbl.color = STATUS_COLORS.get(kind, ui.C_WHITE)

    display.root_group = displayio.Group()
