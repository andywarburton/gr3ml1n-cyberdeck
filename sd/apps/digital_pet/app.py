# apps/digital_pet/app.py
# CyberDeck app: Digital Pet | portrait 240x320
# Hatch an egg and raise a pixel monster companion

import displayio
import terminalio
import vectorio
import time
import os
import gc
import random
import array
import math
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui
import names
import pets

SAMPLE_RATE = 8000

_DATA_DIR  = "/sd/apps/digital_pet/data"
_SAVE_FILE = _DATA_DIR + "/pet_save.txt"
PIXEL      = 5
GRID       = 12
HALF       = (GRID * PIXEL) // 2

EGG_C = {
    "outer":  0xCCBB88,
    "inner":  0xEEDD99,
    "shell":  0xDDBB77,
    "crack":  0x443322,
    "shiny":  0xFFFFDD,
    "dark":   0xAA9955,
}

EGG_BODY = [
    (3*PIXEL, 2*PIXEL, PIXEL, PIXEL, "outer"),
    (4*PIXEL, 1*PIXEL, PIXEL, PIXEL, "outer"),
    (5*PIXEL, 1*PIXEL, PIXEL, PIXEL, "inner"),
    (6*PIXEL, 1*PIXEL, PIXEL, PIXEL, "inner"),
    (7*PIXEL, 2*PIXEL, PIXEL, PIXEL, "outer"),
    (2*PIXEL, 3*PIXEL, PIXEL, PIXEL, "outer"),
    (3*PIXEL, 3*PIXEL, PIXEL, PIXEL, "inner"),
    (4*PIXEL, 3*PIXEL, PIXEL, PIXEL, "inner"),
    (5*PIXEL, 3*PIXEL, PIXEL, PIXEL, "inner"),
    (6*PIXEL, 3*PIXEL, PIXEL, PIXEL, "inner"),
    (7*PIXEL, 3*PIXEL, PIXEL, PIXEL, "inner"),
    (8*PIXEL, 3*PIXEL, PIXEL, PIXEL, "outer"),
    (2*PIXEL, 4*PIXEL, PIXEL, PIXEL, "outer"),
    (3*PIXEL, 4*PIXEL, PIXEL, PIXEL, "shell"),
    (4*PIXEL, 4*PIXEL, PIXEL, PIXEL, "shell"),
    (5*PIXEL, 4*PIXEL, PIXEL, PIXEL, "shell"),
    (6*PIXEL, 4*PIXEL, PIXEL, PIXEL, "shell"),
    (7*PIXEL, 4*PIXEL, PIXEL, PIXEL, "shell"),
    (8*PIXEL, 4*PIXEL, PIXEL, PIXEL, "outer"),
    (1*PIXEL, 5*PIXEL, PIXEL, PIXEL, "outer"),
    (2*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (3*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (4*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (5*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (6*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (7*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (8*PIXEL, 5*PIXEL, PIXEL, PIXEL, "shell"),
    (9*PIXEL, 5*PIXEL, PIXEL, PIXEL, "outer"),
    (1*PIXEL, 6*PIXEL, PIXEL, PIXEL, "outer"),
    (2*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (3*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (4*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (5*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (6*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (7*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (8*PIXEL, 6*PIXEL, PIXEL, PIXEL, "shell"),
    (9*PIXEL, 6*PIXEL, PIXEL, PIXEL, "outer"),
    (1*PIXEL, 7*PIXEL, PIXEL, PIXEL, "outer"),
    (2*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (3*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (4*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (5*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (6*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (7*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (8*PIXEL, 7*PIXEL, PIXEL, PIXEL, "shell"),
    (9*PIXEL, 7*PIXEL, PIXEL, PIXEL, "outer"),
    (2*PIXEL, 8*PIXEL, PIXEL, PIXEL, "outer"),
    (3*PIXEL, 8*PIXEL, PIXEL, PIXEL, "shell"),
    (4*PIXEL, 8*PIXEL, PIXEL, PIXEL, "shell"),
    (5*PIXEL, 8*PIXEL, PIXEL, PIXEL, "shell"),
    (6*PIXEL, 8*PIXEL, PIXEL, PIXEL, "shell"),
    (7*PIXEL, 8*PIXEL, PIXEL, PIXEL, "shell"),
    (8*PIXEL, 8*PIXEL, PIXEL, PIXEL, "outer"),
    (3*PIXEL, 9*PIXEL, PIXEL, PIXEL, "outer"),
    (4*PIXEL, 9*PIXEL, PIXEL, PIXEL, "outer"),
    (5*PIXEL, 9*PIXEL, PIXEL, PIXEL, "dark"),
    (6*PIXEL, 9*PIXEL, PIXEL, PIXEL, "outer"),
    (7*PIXEL, 9*PIXEL, PIXEL, PIXEL, "outer"),
    (4*PIXEL, 2*PIXEL, PIXEL, PIXEL, "shiny"),
    (5*PIXEL, 2*PIXEL, PIXEL, PIXEL, "shiny"),
]

EGG_CRACKS = [
    [(5, 3), (4, 4), (5, 5), (4, 6)],
    [(7, 4), (8, 5), (7, 6), (8, 7)],
    [(3, 7), (4, 8)],
    [(8, 3), (9, 4), (8, 5)],
    [(5, 8), (6, 9), (5, 10)],
]


def _make_tone(freq, volume=0.5):
    import audiocore
    length = max(1, SAMPLE_RATE // freq)
    buf = array.array("H", [0] * length)
    for i in range(length):
        val = int(round(32767 * volume * math.sin(2 * math.pi * i / length)))
        if val < 0:
            val = 0
        elif val > 65535:
            val = 65535
        buf[i] = val
    return audiocore.RawSample(buf, sample_rate=SAMPLE_RATE)


def _ensure_dir():
    try:
        os.listdir(_DATA_DIR)
    except OSError:
        try:
            os.mkdir(_DATA_DIR)
        except OSError:
            pass


def _load_save():
    save = {
        "state": "egg",
        "hatch_at": random.randint(11, 49),
        "taps": 0,
        "monster_type": 0,
        "name": "",
        "gender": "male",
    }
    try:
        with open(_SAVE_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k == "hatch_at" or k == "monster_type":
                        v = int(v)
                    save[k] = v
    except OSError:
        pass
    return save


def _write_save(save):
    try:
        with open(_SAVE_FILE, "w") as f:
            for k, v in save.items():
                f.write("{}={}\n".format(k, v))
        return True
    except OSError:
        return False


def _build_sprite(scene, monster, cx, cy, color_map, group=None):
    if group is None:
        group = displayio.Group()
        scene.append(group)
    for (x, y, w, h, key) in monster["body"]:
        pal = displayio.Palette(1)
        pal[0] = color_map.get(key, 0xFFFFFF)
        r = vectorio.Rectangle(
            pixel_shader=pal,
            x=cx - HALF + x,
            y=cy - HALF + y,
            width=w,
            height=h,
        )
        group.append(r)
    return group


def _update_sprite_pal(palette_map, idle_def, frame):
    for key, colors in idle_def.items():
        if key in palette_map:
            palette_map[key][0] = colors[frame % len(colors)]


class SpriteRenderer:
    def __init__(self, scene, monster, cx, cy):
        self.group = displayio.Group()
        scene.append(self.group)
        self.pal_map = {}
        self.monster = monster
        self.cx = cx
        self.cy = cy
        idle = monster.get("idle", {})
        for (x, y, w, h, key) in monster["body"]:
            if key not in self.pal_map:
                pal = displayio.Palette(1)
                colors = idle.get(key, [0xFFFFFF])
                pal[0] = colors[0]
                self.pal_map[key] = pal
                r = vectorio.Rectangle(
                    pixel_shader=pal,
                    x=cx - HALF + x,
                    y=cy - HALF + y,
                    width=w,
                    height=h,
                )
                self.group.append(r)
            else:
                pal = self.pal_map[key]
                r = vectorio.Rectangle(
                    pixel_shader=pal,
                    x=cx - HALF + x,
                    y=cy - HALF + y,
                    width=w,
                    height=h,
                )
                self.group.append(r)

    def idle_frame(self, frame):
        idle = self.monster.get("idle", {})
        for key, colors in idle.items():
            if key in self.pal_map:
                self.pal_map[key][0] = colors[frame % len(colors)]


def run(display, touch, keyboard, W, H):
    _ensure_dir()
    save = _load_save()
    HAS_AUD = False
    _audio = None
    try:
        import audiobusio, board
        _audio = audiobusio.I2SOut(board.I2S_BCK, board.I2S_LRCK, board.I2S_DIN)
        HAS_AUD = True
    except Exception:
        pass

    def _play_tap():
        if HAS_AUD:
            try:
                _audio.stop()
                _audio.play(_make_tone(880, 0.05, 0.4), loop=False)
            except Exception:
                pass

    def _play_crack():
        if HAS_AUD:
            try:
                _audio.stop()
                _audio.play(_make_tone(220, 0.1, 0.5), loop=False)
            except Exception:
                pass

    def _play_hatch():
        if not HAS_AUD:
            return
        freqs = [262, 330, 392, 523]
        for f in freqs:
            try:
                _audio.stop()
                _audio.play(_make_tone(f, 0.12, 0.5), loop=False)
                time.sleep(0.15)
            except Exception:
                pass

    def _play_boop():
        if HAS_AUD:
            try:
                _audio.stop()
                _audio.play(_make_tone(440, 0.08, 0.4), loop=False)
            except Exception:
                pass

    try:
        if save["state"] == "egg":
            _run_egg(display, touch, keyboard, W, H, save, _play_tap, _play_crack, _play_hatch)
        else:
            _run_monster(display, touch, keyboard, W, H, save, _play_boop)
    finally:
        if _audio:
            try:
                _audio.stop()
            except Exception:
                pass
            try:
                _audio.deinit()
            except Exception:
                pass
        display.root_group = displayio.Group()
        gc.collect()


def _run_egg(display, touch, keyboard, W, H, save, _play_tap, _play_crack, _play_hatch):
    taps = save.get("taps", 0)
    hatch_at = save.get("hatch_at", random.randint(11, 49))

    egg_cx = W // 2
    egg_cy = 160

    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:DIGITAL PET", "v1.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    EGG_COLOR_MAP = {
        "outer": EGG_C["outer"],
        "inner": EGG_C["inner"],
        "shell": EGG_C["shell"],
        "crack": EGG_C["crack"],
        "shiny": EGG_C["shiny"],
        "dark":  EGG_C["dark"],
    }

    egg_group = displayio.Group()
    scene.append(egg_group)
    crack_groups = []

    def _build_egg():
        for (x, y, w, h, key) in EGG_BODY:
            pal = displayio.Palette(1)
            pal[0] = EGG_COLOR_MAP.get(key, EGG_C["outer"])
            r = vectorio.Rectangle(
                pixel_shader=pal,
                x=egg_cx - HALF + x,
                y=egg_cy - HALF + y,
                width=w,
                height=h,
            )
            egg_group.append(r)

    _build_egg()

    tap_lbl = label.Label(terminalio.FONT,
                          text="TAPS: {}/{}".format(taps, hatch_at),
                          color=ui.C_GREEN_MID, scale=1)
    tap_lbl.anchor_point = (0.5, 0.5)
    tap_lbl.anchored_position = (W // 2, 248)
    scene.append(tap_lbl)

    hint_lbl = label.Label(terminalio.FONT,
                           text="TAP THE EGG!",
                           color=ui.C_GREEN_DIM, scale=1)
    hint_lbl.anchor_point = (0.5, 0.5)
    hint_lbl.anchored_position = (W // 2, 265)
    scene.append(hint_lbl)

    ui.make_footer(scene, "ESC or SWIPE UP to quit")
    display.root_group = scene

    crack_count = [0]

    def _add_crack(idx):
        if idx >= len(EGG_CRACKS):
            return
        for (gx, gy) in EGG_CRACKS[idx]:
            pal = displayio.Palette(1)
            pal[0] = EGG_C["crack"]
            r = vectorio.Rectangle(
                pixel_shader=pal,
                x=egg_cx - HALF + gx * PIXEL,
                y=egg_cy - HALF + gy * PIXEL,
                width=PIXEL,
                height=PIXEL,
            )
            scene.append(r)
            crack_groups.append(r)
        crack_count[0] = idx + 1

    for i in range(min(5, crack_count[0])):
        _add_crack(i)

    wiggle = [0]
    is_wiggling = [False]
    wiggle_start = [0.0]

    finger_down = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                save["taps"] = taps
                _write_save(save)
                break

        now = time.monotonic()
        if is_wiggling[0]:
            elapsed = now - wiggle_start[0]
            if elapsed < 0.3:
                wiggle[0] = int(round(4 * math.sin(elapsed * 40)))
            else:
                wiggle[0] = 0
                is_wiggling[0] = False
        egg_group.x = wiggle[0]

        x, y, tch = touch.read()
        time.sleep(0.03)

        if tch:
            lx, ly = x, y
            if not finger_down:
                finger_down = True
                sx, sy = x, y
        elif finger_down:
            finger_down = False
            g = classify_gesture(sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
            if g and g[0] == "SWIPE UP":
                save["taps"] = taps
                _write_save(save)
                break
            if g and g[0] == "TAP":
                tx, ty = sx, sy
                ex = egg_cx + 35
                ey = egg_cy + 40
                if abs(tx - egg_cx) < 40 and abs(ty - egg_cy) < 45:
                    taps += 1
                    tap_lbl.text = "TAPS: {}/{}".format(taps, hatch_at)
                    is_wiggling[0] = True
                    wiggle_start[0] = now
                    _play_tap()

                    new_cracks = min(5, taps // 5)
                    if new_cracks > crack_count[0]:
                        _add_crack(crack_count[0])
                        _play_crack()

                    if taps >= hatch_at:
                        save["state"] = "hatched"
                        save["taps"] = 0
                        save["hatch_at"] = random.randint(11, 49)
                        _write_save(save)
                        _run_hatch(display, touch, keyboard, W, H,
                                   save, _play_hatch)
                        return

    display.root_group = displayio.Group()
    del scene
    gc.collect()


def _run_hatch(display, touch, keyboard, W, H, save, _play_hatch):
    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:DIGITAL PET", "v1.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    egg_cx = W // 2
    egg_cy = 160

    egg_l = displayio.Group()
    egg_r = displayio.Group()
    scene.append(egg_l)
    scene.append(egg_r)

    EGG_CM = {
        "outer": EGG_C["outer"],
        "inner": EGG_C["inner"],
        "shell": EGG_C["shell"],
        "crack": EGG_C["crack"],
        "shiny": EGG_C["shiny"],
        "dark":  EGG_C["dark"],
    }

    for (x, y, w, h, key) in EGG_BODY:
        if x + w // 2 < 6 * PIXEL:
            pal = displayio.Palette(1)
            pal[0] = EGG_CM.get(key, EGG_C["outer"])
            egg_l.append(vectorio.Rectangle(
                pixel_shader=pal,
                x=egg_cx - HALF + x,
                y=egg_cy - HALF + y,
                width=w, height=h,
            ))
        else:
            pal = displayio.Palette(1)
            pal[0] = EGG_CM.get(key, EGG_C["outer"])
            egg_r.append(vectorio.Rectangle(
                pixel_shader=pal,
                x=egg_cx - HALF + x,
                y=egg_cy - HALF + y,
                width=w, height=h,
            ))

    flash_bg = displayio.Group()
    ui.solid_rect(flash_bg, 0, 0, W, H, 0xFFFFFF)
    flash_bg.hidden = True
    scene.append(flash_bg)

    congrats_lbl = label.Label(terminalio.FONT,
                                text="HATCHED!",
                                color=ui.C_GREEN_HI, scale=2)
    congrats_lbl.anchor_point = (0.5, 0.5)
    congrats_lbl.anchored_position = (W // 2, 260)
    congrats_lbl.hidden = True
    scene.append(congrats_lbl)

    display.root_group = scene
    _play_hatch()

    start = time.monotonic()
    monster_shown = False

    monster_type = random.randint(0, len(pets.MONSTERS) - 1)
    monster = pets.MONSTERS[monster_type]

    gender = random.choice(["male", "female"])
    if gender == "male":
        pet_name = random.choice(names.MALE_NAMES)
    else:
        pet_name = random.choice(names.FEMALE_NAMES)

    save["state"] = "hatched"
    save["monster_type"] = monster_type
    save["name"] = pet_name
    save["gender"] = gender
    _write_save(save)

    renderer = None

    while True:
        now = time.monotonic()
        elapsed = now - start

        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        if elapsed < 1.2:
            shake = int(round(5 * math.sin(elapsed * 30)))
            egg_l.x = -10 + shake
            egg_r.x = 10 + shake
            egg_l.y = shake // 2
            egg_r.y = -shake // 2
        elif elapsed < 1.5:
            egg_l.x = -30
            egg_l.y = 0
            egg_r.x = 30
            egg_r.y = 0
        elif elapsed < 1.7:
            flash_bg.hidden = False
        elif elapsed < 2.0:
            flash_bg.hidden = True
            egg_l.hidden = True
            egg_r.hidden = True
        elif elapsed < 2.2:
            pass
        else:
            if not monster_shown:
                egg_l.hidden = True
                egg_r.hidden = True
                flash_bg.hidden = True
                renderer = SpriteRenderer(scene, monster, W // 2, 155)
                congrats_lbl.hidden = False
                monster_shown = True
                start = now
            else:
                frame = int(round((now - start) * 2)) % 3
                if renderer:
                    renderer.idle_frame(frame)

        time.sleep(0.03)

    display.root_group = displayio.Group()
    del scene
    gc.collect()


def _run_monster(display, touch, keyboard, W, H, save, _play_boop):
    monster_type = save.get("monster_type", 0)
    monster_type = min(monster_type, len(pets.MONSTERS) - 1)
    monster = pets.MONSTERS[monster_type]
    pet_name = save.get("name", "???")
    gender = save.get("gender", "male")

    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:DIGITAL PET", "v1.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    name_lbl = label.Label(terminalio.FONT,
                           text="{} ({})".format(pet_name.upper(), gender.upper()),
                           color=ui.C_GREEN_HI, scale=1)
    name_lbl.anchor_point = (0.5, 0.5)
    name_lbl.anchored_position = (W // 2, 80)
    scene.append(name_lbl)

    type_lbl = label.Label(terminalio.FONT,
                           text="TYPE: {}".format(monster["name"].upper()),
                           color=ui.C_GREEN_MID, scale=1)
    type_lbl.anchor_point = (0.5, 0.5)
    type_lbl.anchored_position = (W // 2, 96)
    scene.append(type_lbl)

    cx = W // 2
    cy = 175

    renderer = SpriteRenderer(scene, monster, cx, cy)

    tap_lbl = label.Label(terminalio.FONT,
                          text="TAP TO PLAY",
                          color=ui.C_GREEN_DIM, scale=1)
    tap_lbl.anchor_point = (0.5, 0.5)
    tap_lbl.anchored_position = (W // 2, 248)
    scene.append(tap_lbl)

    ui.make_footer(scene, "ESC or SWIPE UP to quit")
    display.root_group = scene

    bounce_y = [0]
    bounce_v = [0.0]
    is_bouncing = [False]
    idle_start = time.monotonic()

    finger_down = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        now = time.monotonic()

        idle_phase = int(round((now - idle_start) * 2)) % 3
        renderer.idle_frame(idle_phase)

        if is_bouncing[0]:
            bounce_v[0] -= 1.5
            bounce_y[0] = int(round(bounce_y[0] + bounce_v[0]))
            if bounce_y[0] >= 0:
                bounce_y[0] = 0
                bounce_v[0] = 0.0
                is_bouncing[0] = False
        else:
            bob = int(round(2 * math.sin(now * 1.5)))
            bounce_y[0] = bob

        renderer.group.y = bounce_y[0]

        x, y, tch = touch.read()
        time.sleep(0.03)

        if tch:
            lx, ly = x, y
            if not finger_down:
                finger_down = True
                sx, sy = x, y
        elif finger_down:
            finger_down = False
            g = classify_gesture(sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
            if g and g[0] == "SWIPE UP":
                break
            if g and g[0] == "TAP":
                tx, ty = sx, sy
                if abs(tx - cx) < 50 and abs(ty - cy) < 55:
                    if not is_bouncing[0]:
                        is_bouncing[0] = True
                        bounce_v[0] = 8
                    _play_boop()

    display.root_group = displayio.Group()
    del scene
    gc.collect()
