# apps/key_test/app.py
# CyberDeck app: Keyboard HID Tester | portrait 240×320
#
# Press any key to display it as large as possible with its HID keycode.
# ESC does not exit — swipe up to quit.

import displayio
import terminalio
import time
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui
from battery_monitor import BatteryMonitor
import timekeeper


def _scale_for(name):
    n = len(name)
    if n == 1:  return 8
    if n <= 3:  return 7
    if n <= 5:  return 6
    return 5


def run(display, touch, keyboard, W, H):
    batt = BatteryMonitor()
    scene = displayio.Group()
    ui.make_title_bar(scene, "KEY TEST", "HID",
        time_str=timekeeper.now_str(),
        battery_str="{:.1f}V".format(batt.voltage) if batt.voltage > 0.1 else "")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # Large key label — centred slightly above mid
    key_lbl = label.Label(terminalio.FONT, text="?", color=ui.C_GREEN_HI, scale=8)
    key_lbl.anchor_point = (0.5, 0.5)
    key_lbl.anchored_position = (W // 2, 148)
    scene.append(key_lbl)

    # Keycode label — below the key label
    code_lbl = label.Label(terminalio.FONT, text="HID CODE: ---", color=ui.C_GREEN_MID, scale=2)
    code_lbl.anchor_point = (0.5, 0.5)
    code_lbl.anchored_position = (W // 2, 228)
    scene.append(code_lbl)

    hint_lbl = label.Label(terminalio.FONT, text="PRESS A KEY", color=ui.C_GREEN_DIM, scale=1)
    hint_lbl.anchor_point = (0.5, 0.5)
    hint_lbl.anchored_position = (W // 2, 262)
    scene.append(hint_lbl)

    ui.make_footer(scene, "SWIPE UP TO EXIT")
    display.root_group = scene

    finger_down = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()

            key_name = None
            if kbd['escape']:   key_name = "ESC"
            elif kbd['enter']:  key_name = "ENTER"
            elif kbd['delete']: key_name = "DEL"
            elif kbd['up']:     key_name = "UP"
            elif kbd['down']:   key_name = "DOWN"
            elif kbd['left']:   key_name = "LEFT"
            elif kbd['right']:  key_name = "RIGHT"
            elif kbd['char']:   key_name = kbd['char'].upper()

            if key_name is not None:
                key_lbl.scale = _scale_for(key_name)
                key_lbl.text  = key_name
                if kbd['keycode'] is not None:
                    code_lbl.text = "HID CODE: {}".format(kbd['keycode'])
                hint_lbl.text = " "

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

    display.root_group = displayio.Group()
