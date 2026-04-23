# apps/battery_test/app.py
# CyberDeck app: Battery Voltage Monitor | portrait 240x320

import displayio
import terminalio
import time
from adafruit_display_text import label
from waveshare_touch import classify_gesture
from battery_monitor import BatteryMonitor
import timekeeper
import cyber_ui as ui


def run(display, touch, keyboard, W, H):
    batt = BatteryMonitor()

    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:BATTERY", time_str=timekeeper.now_str())
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # ── Decorative border box ─────────────────────────────────────────────────
    bx, by, bw, bh = 10, 45, W - 20, 100
    ui.make_border(scene, bx, by, bw, bh, ui.C_GREEN_MID)
    ui.make_border(scene, bx + 2, by + 2, bw - 4, bh - 4, ui.C_GREEN_DIM)
    for cx, cy in [(bx, by), (bx + bw - 8, by),
                   (bx, by + bh - 8), (bx + bw - 8, by + bh - 8)]:
        ui.solid_rect(scene, cx, cy, 8, 8, ui.C_GREEN_MID)

    # ── Voltage readout ───────────────────────────────────────────────────────
    volt_lbl = label.Label(terminalio.FONT, text="--.-- V",
                           color=ui.C_GREEN_HI, scale=3)
    volt_lbl.anchor_point = (0.5, 0.5)
    volt_lbl.anchored_position = (W // 2, 92)
    scene.append(volt_lbl)

    # ── Percentage readout ────────────────────────────────────────────────────
    pct_lbl = label.Label(terminalio.FONT, text="---%",
                          color=ui.C_GREEN_DIM, scale=2)
    pct_lbl.anchor_point = (0.5, 0.5)
    pct_lbl.anchored_position = (W // 2, 130)
    scene.append(pct_lbl)

    # ── Source & charge status ────────────────────────────────────────────────
    source_lbl = label.Label(terminalio.FONT, text="SRC: --",
                             color=ui.C_GREEN_DIM, scale=1)
    source_lbl.anchor_point = (0.5, 0.5)
    source_lbl.anchored_position = (W // 2, 162)
    scene.append(source_lbl)

    charge_lbl = label.Label(terminalio.FONT, text="CHG: --",
                             color=ui.C_GREEN_DIM, scale=1)
    charge_lbl.anchor_point = (0.5, 0.5)
    charge_lbl.anchored_position = (W // 2, 180)
    scene.append(charge_lbl)

    # ── Status line ───────────────────────────────────────────────────────────
    status_lbl = label.Label(terminalio.FONT,
                             text="[ INITIALIZING ]",
                             color=ui.C_AMBER, scale=1)
    status_lbl.anchor_point = (0.5, 0.5)
    status_lbl.anchored_position = (W // 2, 210)
    scene.append(status_lbl)

    # ── Digital pin states ────────────────────────────────────────────────────
    ctrl_lbl = label.Label(terminalio.FONT,
                           text="CTRL: --",
                           color=ui.C_GREEN_DIM, scale=1)
    ctrl_lbl.anchor_point = (0.5, 0.5)
    ctrl_lbl.anchored_position = (W // 2, 232)
    scene.append(ctrl_lbl)

    pwr_lbl = label.Label(terminalio.FONT,
                          text="PWR: --",
                          color=ui.C_GREEN_DIM, scale=1)
    pwr_lbl.anchor_point = (0.5, 0.5)
    pwr_lbl.anchored_position = (W // 2, 252)
    scene.append(pwr_lbl)

    ui.make_footer(scene, "ESC or SWIPE UP to quit")
    display.root_group = scene

    finger_down = False
    sx = sy = lx = ly = 0
    last_update = 0

    while True:
        now = time.monotonic()

        # ── Keyboard ──────────────────────────────────────────────────────────
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        # ── Touch ─────────────────────────────────────────────────────────────
        x, y, touching = touch.read()

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

        # ── Update readout every 0.5s ─────────────────────────────────────────
        if now - last_update >= 0.5:
            last_update = now
            data = batt.read()

            v = data["voltage"]
            pct = data["percentage"]
            src = data["power_source"]
            chg = data["is_charging"]
            ctrl = data["ctrl_state"]
            pwr = data["pwr_state"]

            # Voltage
            if v > 0.1:
                volt_lbl.text = "{:.2f} V".format(v)
            else:
                volt_lbl.text = "--.-- V"

            # Percentage / USB indicator
            if pct == -1:
                pct_lbl.text = "USB"
                pct_lbl.color = ui.C_AMBER
            elif pct >= 0:
                pct_lbl.text = "{:d}%".format(pct)
            else:
                pct_lbl.text = "---%"
                pct_lbl.color = ui.C_GREEN_DIM

            # Source
            source_lbl.text = "SRC: " + src

            # Charging
            if chg:
                charge_lbl.text = "CHG: YES"
                charge_lbl.color = ui.C_GREEN_HI
            else:
                charge_lbl.text = "CHG: NO"
                charge_lbl.color = ui.C_GREEN_DIM

            # Status & colors
            if src == "USB":
                status_lbl.text = "[ USB POWER ]"
                status_lbl.color = ui.C_AMBER
                volt_lbl.color = ui.C_AMBER
            elif v >= 3.6:
                status_lbl.text = "[ NOMINAL ]"
                status_lbl.color = ui.C_GREEN_HI
                volt_lbl.color = ui.C_GREEN_HI
                pct_lbl.color = ui.C_GREEN_HI
            elif v >= 3.3:
                status_lbl.text = "[ LOW BATTERY ]"
                status_lbl.color = ui.C_AMBER
                volt_lbl.color = ui.C_AMBER
                pct_lbl.color = ui.C_AMBER
            elif v > 0.1:
                status_lbl.text = "[ CRITICAL ]"
                status_lbl.color = ui.C_RED
                volt_lbl.color = ui.C_RED
                pct_lbl.color = ui.C_RED
            else:
                status_lbl.text = "[ NO BATTERY ]"
                status_lbl.color = ui.C_RED_DIM
                volt_lbl.color = ui.C_GREEN_DIM

            # Digital pins
            ctrl_lbl.text = "CTRL: " + ("HIGH" if ctrl else "LOW" if ctrl is False else "--")
            pwr_lbl.text = "PWR: " + ("HIGH" if pwr else "LOW" if pwr is False else "--")

        time.sleep(0.04)

    batt.deinit()
    display.root_group = displayio.Group()
