# apps/ble_scanner/app.py
# CyberDeck app: BLE Scanner | portrait 240x320
# Scans for nearby Bluetooth Low Energy devices

import displayio
import terminalio
import time
import gc
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

try:
    from adafruit_ble import BLERadio
    print("ble_scanner: adafruit_ble imported OK")
    _HAS_BLE = True
except Exception as e:
    print("ble_scanner: adafruit_ble import FAILED:", e)
    _HAS_BLE = False


def run(display, touch, keyboard, W, H):
    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:BT SCANNER", "v1.0")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    if not _HAS_BLE:
        err_lbl = label.Label(terminalio.FONT,
            text="BLE NOT AVAILABLE",
            color=ui.C_RED, scale=2)
        err_lbl.anchor_point = (0.5, 0.5)
        err_lbl.anchored_position = (W // 2, H // 2 - 20)
        sc.append(err_lbl)

        msg_lbl = label.Label(terminalio.FONT,
            text="Install adafruit_ble library",
            color=ui.C_AMBER, scale=1)
        msg_lbl.anchor_point = (0.5, 0.5)
        msg_lbl.anchored_position = (W // 2, H // 2 + 20)
        sc.append(msg_lbl)

        ui.make_footer(sc, "ESC to quit")
        display.root_group = sc

        while True:
            if keyboard:
                kbd = keyboard.poll()
                if kbd['escape']:
                    break
            time.sleep(0.1)
        display.root_group = displayio.Group()
        return

    status_lbl = label.Label(terminalio.FONT,
        text="INITIALIZING...",
        color=ui.C_GREEN_DIM, scale=1)
    status_lbl.anchor_point = (0.5, 0.5)
    status_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 40)
    sc.append(status_lbl)

    scan_lbl = label.Label(terminalio.FONT,
        text="SCANNING...",
        color=ui.C_AMBER, scale=2)
    scan_lbl.anchor_point = (0.5, 0.5)
    scan_lbl.anchored_position = (W // 2, H // 2)
    sc.append(scan_lbl)

    ui.make_footer(sc, "ESC or SWIPE UP to quit")
    display.root_group = sc

    try:
        print("ble_scanner: Creating BLERadio()")
        ble = BLERadio()
        print("ble_scanner: BLERadio created OK")
    except Exception as e:
        print("ble_scanner: BLERadio FAILED:", e)
        scan_lbl.text = "BLE ERROR"
        scan_lbl.color = ui.C_RED
        time.sleep(3)
        display.root_group = displayio.Group()
        return

    devices = []
    max_devices = 8

    device_labels = []
    for i in range(max_devices):
        y_pos = ui.CONTENT_Y + 60 + i * 28
        lbl = label.Label(terminalio.FONT, text=" ",
                         color=ui.C_GREEN, scale=1)
        lbl.anchor_point = (0.0, 0.0)
        lbl.anchored_position = (8, y_pos)
        sc.append(lbl)
        device_labels.append(lbl)

    count_lbl = label.Label(terminalio.FONT, text="",
                           color=ui.C_GREEN_DIM, scale=1)
    count_lbl.anchor_point = (0.5, 0.5)
    count_lbl.anchored_position = (W // 2, 270)
    sc.append(count_lbl)

    scan_lbl.text = ""
    status_lbl.text = "FOUND:"
    status_lbl.color = ui.C_GREEN_HI
    count_lbl.text = "0 devices"

    scan_start = time.monotonic()
    scan_duration = 10.0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        x, y, tch = touch.read()

        if tch:
            pass
        elif time.monotonic() - scan_start >= scan_duration:
            break

        try:
            ble.stop_scan()
            for advertisement in ble.start_scan(timeout=1.0, interval=0.1):
                addr = str(advertisement.address)
                name = advertisement.complete_name or advertisement.short_name or "Unknown"
                rssi = advertisement.rssi
                print("ble_scanner: Found:", name, "|", addr, "| RSSI:", rssi)

                for dev in devices:
                    if dev['addr'] == addr:
                        dev['rssi'] = rssi
                        break
                else:
                    devices.append({
                        'addr': addr,
                        'name': name,
                        'rssi': rssi,
                    })
                    count_lbl.text = str(len(devices)) + " devices"

                if len(devices) >= max_devices:
                    break
            ble.stop_scan()
        except Exception as e:
            print("ble_scanner: Scan error:", e)
            try:
                ble.stop_scan()
            except:
                pass

        for i, lbl in enumerate(device_labels):
            if i < len(devices):
                dev = devices[i]
                rssi_bar = ""
                if dev['rssi'] < -80:
                    rssi_bar = "-"
                elif dev['rssi'] < -70:
                    rssi_bar = "--"
                elif dev['rssi'] < -60:
                    rssi_bar = "---"
                elif dev['rssi'] < -50:
                    rssi_bar = "----"
                else:
                    rssi_bar = "-----"
                lbl.text = rssi_bar + " " + dev['name'][:12]
            else:
                lbl.text = " "

        time.sleep(0.1)

    scan_lbl.text = "DONE"
    scan_lbl.color = ui.C_GREEN_HI

    try:
        ble.stop_scan()
    except:
        pass

    time.sleep(1)

    display.root_group = displayio.Group()
    del sc
    gc.collect()
