# code.py - CyberDeck OS Launcher
# Waveshare ESP32-S3 Touch LCD 2.8 | PORTRAIT 240×320 | CircuitPython 10.x
#
# Auto-discovers apps in /sd/apps/ (SD card) with /apps/ (flash) as fallback.
# Each app folder must contain manifest.json + app.py with run(display,touch,W,H).

print("""
  _   _ ___ _  _ ___ 
 | | | | __| \\| | __|
 | |_| | _|| .` | _| 
  \\___/|___|_|\\_|___|
 Mini Cyberdeck OS
""")

import board
import displayio
import terminalio
import time
import os
import json
import gc

from adafruit_display_text import label
from waveshare_touch import WaveshareTouch, classify_gesture
from uart_keyboard import get_keyboard
import cyber_ui as ui

# ── Portrait mode ──────────────────────────────────────────────────────────────
# rotation=90  → 90° clockwise  (right side of landscape becomes top of portrait)
# rotation=270 → 90° counter-clockwise (swap if display appears upside-down)
_ROTATION = 90

display = board.DISPLAY
display.rotation = _ROTATION
W = display.width    # 240 after rotation
H = display.height   # 320 after rotation

touch = WaveshareTouch(board.TP_SCL, board.TP_SDA, board.TP_RST, rotation=_ROTATION)

# ── Boot animation ─────────────────────────────────────────────────────────────
_boot = displayio.Group()
ui.boot_glitch(display, _boot)
gc.collect()

# ── App paths ─────────────────────────────────────────────────────────────────
APPS_PATHS = ["/sd/apps", "/apps"]   # SD card first, flash as fallback

# ── Menu constants ─────────────────────────────────────────────────────────────
TILE_H   = 42
TILE_GAP = 3
MAX_VIS  = 5   # max tiles visible per page in portrait


# ── App discovery ──────────────────────────────────────────────────────────────
def discover_apps():
    apps = []
    seen = set()
    for base in APPS_PATHS:
        try:
            entries = os.listdir(base)
        except OSError:
            continue
        for entry in sorted(entries):
            if entry in seen:
                continue
            mf = base + "/" + entry + "/manifest.json"
            try:
                with open(mf) as f:
                    manifest = json.load(f)
                manifest["_path"] = base + "/" + entry
                apps.append(manifest)
                seen.add(entry)
            except (OSError, ValueError):
                pass
    apps.sort(key=lambda a: (a.get("order", 99), a.get("name", "")))
    return apps


# ── Error screen ───────────────────────────────────────────────────────────────
def show_error(msg):
    err = displayio.Group()
    ui.solid_rect(err, 0, 0, W, H, ui.C_RED_DIM)
    e_lbl = label.Label(terminalio.FONT, text="!! ERROR !!", color=ui.C_RED, scale=2)
    e_lbl.anchor_point = (0.5, 0.5)
    e_lbl.anchored_position = (W // 2, H // 2 - 20)
    err.append(e_lbl)
    m_lbl = label.Label(terminalio.FONT, text=msg[:28], color=ui.C_AMBER, scale=1)
    m_lbl.anchor_point = (0.5, 0.5)
    m_lbl.anchored_position = (W // 2, H // 2 + 12)
    err.append(m_lbl)
    display.root_group = err
    time.sleep(3)
    del err
    gc.collect()


# ── App launch engine ──────────────────────────────────────────────────────────
def launch_app(app, keyboard):
    g = {"keyboard": keyboard}
    try:
        with open(app["_path"] + "/app.py") as f:
            exec(f.read(), g)  # noqa: S102
        if "run" in g:
            g["run"](display, touch, keyboard, W, H)
        else:
            show_error("No run() in " + app.get("name", "?"))
    except MemoryError:
        gc.collect()
        show_error("OUT OF MEMORY")
    except Exception as e:
        show_error(str(e)[:28])
    finally:
        del g
        gc.collect()
        gc.collect()


# ── Multi-row tile hit test ────────────────────────────────────────────────────
def tap_to_app(sx, sy, tiles):
    for tile in tiles:
        if tile["ty"] <= sy <= tile["ty"] + TILE_H:
            return tile["app"]
    return None


# ── Build menu scene ───────────────────────────────────────────────────────────
def build_scene(apps, page, selected_idx=0):
    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:LAUNCHER", "CYBERDECK OS")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    total_pages = max(1, (len(apps) + MAX_VIS - 1) // MAX_VIS)
    start   = page * MAX_VIS
    visible = apps[start : start + MAX_VIS]

    tiles = []
    if visible:
        stack_h = len(visible) * TILE_H + (len(visible) - 1) * TILE_GAP
        top_pad = (ui.CONTENT_H - stack_h) // 2
        top_y   = ui.CONTENT_Y + top_pad

        for i, app in enumerate(visible):
            ty = top_y + i * (TILE_H + TILE_GAP)
            global_idx = start + i
            is_selected = (global_idx == selected_idx)
            color = ui.C_GREEN_HI if is_selected else ui.C_GREEN_DIM
            pal = ui.solid_rect(scene, 2, ty, W - 4, TILE_H, ui.C_BG_PANEL)
            ui.make_border(scene, 2, ty, W - 4, TILE_H, color)

            n_lbl = label.Label(terminalio.FONT,
                text="> " + app.get("name", "???")[:20],
                color=color, scale=1)
            n_lbl.anchor_point = (0.0, 0.0)
            n_lbl.anchored_position = (8, ty + 5)
            scene.append(n_lbl)

            desc = app.get("description", "")[:28]
            if desc:
                d_lbl = label.Label(terminalio.FONT, text=desc,
                    color=color, scale=1)
                d_lbl.anchor_point = (0.0, 1.0)
                d_lbl.anchored_position = (8, ty + TILE_H - 5)
                scene.append(d_lbl)

            tiles.append({"ty": ty, "app": app, "pal": pal, "idx": global_idx})
    else:
        msg = label.Label(terminalio.FONT, text="NO APPS FOUND",
            color=ui.C_GREEN_DIM, scale=2)
        msg.anchor_point = (0.5, 0.5)
        msg.anchored_position = (W // 2, ui.CONTENT_Y + ui.CONTENT_H // 2)
        scene.append(msg)

    if total_pages > 1:
        footer_hint = "SPACE/BKSP=PAGE  |  UP/DOWN+ENTER"
    else:
        footer_hint = "UP/DOWN=NAV  |  ENTER=LAUNCH  |  ESC=REFRESH"
    ui.make_footer(scene, footer_hint)

    return scene, tiles, total_pages


# ── Main launcher loop ─────────────────────────────────────────────────────────
def run_launcher():
    apps = discover_apps()
    page = 0
    selected_idx = 0
    keyboard = get_keyboard()

    while True:
        scene, tiles, total_pages = build_scene(apps, page, selected_idx)
        display.root_group = scene
        gc.collect()

        finger_down  = False
        start_x = start_y = last_x = last_y = 0
        selected_app = None
        rebuild = False

        while selected_app is None and not rebuild:
            x, y, touching = touch.read()
            kbd = keyboard.poll()

            if kbd['down']:
                selected_idx = min(selected_idx + 1, len(apps) - 1)
                new_page = selected_idx // MAX_VIS
                if new_page != page:
                    page = new_page
                rebuild = True
            elif kbd['up']:
                selected_idx = max(selected_idx - 1, 0)
                new_page = selected_idx // MAX_VIS
                if new_page != page:
                    page = new_page
                rebuild = True
            elif kbd['enter']:
                selected_app = apps[selected_idx]
            elif kbd['escape']:
                apps = discover_apps()
                selected_idx = min(selected_idx, len(apps) - 1)
                rebuild = True
            elif kbd['char'] == ' ' and total_pages > 1:
                page = min(page + 1, total_pages - 1)
                rebuild = True
            elif kbd['delete'] and total_pages > 1:
                page = max(page - 1, 0)
                rebuild = True

            if touching:
                last_x, last_y = x, y
                if not finger_down:
                    finger_down = True
                    start_x, start_y = x, y
            elif finger_down:
                finger_down = False

                action = classify_gesture(
                    start_x, start_y, last_x, last_y, W, H,
                    swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN,
                )
                if action:
                    name = action[0]
                    if name == "SWIPE LEFT" and total_pages > 1:
                        page = min(page + 1, total_pages - 1)
                        rebuild = True
                    elif name == "SWIPE RIGHT" and total_pages > 1:
                        page = max(page - 1, 0)
                        rebuild = True
                    elif name == "SWIPE UP":
                        apps = discover_apps()
                        selected_idx = min(selected_idx, len(apps) - 1)
                        rebuild = True
                    elif name == "TAP":
                        selected_app = tap_to_app(start_x, start_y, tiles)

            time.sleep(0.04)

        del scene
        gc.collect()

        if selected_app is not None:
            launch_app(selected_app, keyboard)


run_launcher()
