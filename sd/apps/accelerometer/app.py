# apps/accelerometer/app.py
# CyberDeck app: Accelerometer display | portrait 240x320

import displayio
import terminalio
import busio
import time
import gc
import board
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

try:
    import qmi8658c
    _HAS_IMU = True
except Exception:
    _HAS_IMU = False


def run(display, touch, W, H):
    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:ACCEL", "G-FORCE")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    x_lbl = label.Label(terminalio.FONT, text="X: +0.00", color=ui.C_GREEN_HI, scale=1)
    x_lbl.anchor_point = (0.0, 0.0)
    x_lbl.anchored_position = (8, 30)
    scene.append(x_lbl)

    y_lbl = label.Label(terminalio.FONT, text="Y: +0.00", color=ui.C_GREEN_HI, scale=1)
    y_lbl.anchor_point = (0.0, 0.0)
    y_lbl.anchored_position = (8, 70)
    scene.append(y_lbl)

    z_lbl = label.Label(terminalio.FONT, text="Z: +0.00", color=ui.C_GREEN_HI, scale=1)
    z_lbl.anchor_point = (0.0, 0.0)
    z_lbl.anchored_position = (8, 110)
    scene.append(z_lbl)

    ui.make_border(scene, 6, 28, W - 12, 96, ui.C_GREEN_DIM)

    mag_lbl = label.Label(terminalio.FONT, text="MAGNITUDE: 1.00G", color=ui.C_AMBER, scale=2)
    mag_lbl.anchor_point = (0.5, 0.5)
    mag_lbl.anchored_position = (W // 2, 180)
    scene.append(mag_lbl)

    orientation_lbl = label.Label(terminalio.FONT, text="[ FLAT ]", color=ui.C_GREEN_DIM, scale=1)
    orientation_lbl.anchor_point = (0.5, 0.5)
    orientation_lbl.anchored_position = (W // 2, 220)
    scene.append(orientation_lbl)

    imu = None
    if _HAS_IMU:
        try:
            i2c = busio.I2C(board.IO10, board.IO11)
            imu = qmi8658c.QMI8658C(i2c)
        except Exception as e:
            err_lbl = label.Label(terminalio.FONT, text=f"IMU ERR: {str(e)[:20]}", color=ui.C_RED, scale=1)
            err_lbl.anchor_point = (0.5, 0.5)
            err_lbl.anchored_position = (W // 2, 260)
            scene.append(err_lbl)
            imu = None
    else:
        err_lbl = label.Label(terminalio.FONT, text="IMU NOT FOUND", color=ui.C_RED, scale=1)
        err_lbl.anchor_point = (0.5, 0.5)
        err_lbl.anchored_position = (W // 2, 260)
        scene.append(err_lbl)

    ui.make_footer(scene, "^ SWIPE UP to quit")
    display.root_group = scene

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

        if imu is not None:
            try:
                ax, ay, az = imu.acceleration
                ax_g = ax / 9.806
                ay_g = ay / 9.806
                az_g = az / 9.806

                x_lbl.text = f"X: {ax_g:+.2f}G"
                y_lbl.text = f"Y: {ay_g:+.2f}G"
                z_lbl.text = f"Z: {az_g:+.2f}G"

                magnitude = (ax_g**2 + ay_g**2 + az_g**2) ** 0.5
                mag_lbl.text = f"MAG: {magnitude:.2f}G"

                if abs(az_g) > 0.8 and abs(ax_g) < 0.3 and abs(ay_g) < 0.3:
                    orient = "[ FLAT ]"
                    mag_lbl.color = ui.C_GREEN_HI
                elif ax_g > 0.7:
                    orient = "[ TILT RIGHT ]"
                    mag_lbl.color = ui.C_AMBER
                elif ax_g < -0.7:
                    orient = "[ TILT LEFT ]"
                    mag_lbl.color = ui.C_AMBER
                elif ay_g > 0.7:
                    orient = "[ TILT FWD ]"
                    mag_lbl.color = ui.C_AMBER
                elif ay_g < -0.7:
                    orient = "[ TILT BACK ]"
                    mag_lbl.color = ui.C_AMBER
                elif az_g < -0.5:
                    orient = "[ UPSIDE DOWN ]"
                    mag_lbl.color = ui.C_RED
                else:
                    orient = "[ ANGLED ]"
                    mag_lbl.color = ui.C_GREEN_DIM
                orientation_lbl.text = orient
            except Exception:
                pass

    display.root_group = displayio.Group()
    gc.collect()
