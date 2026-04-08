# apps/mini_synth/app.py
# CyberDeck app: Mini Synth | portrait 240x320
#
# 8-note honeycomb keyboard (C4-C5) in a 3-2-3 arrangement
# I2S audio via board.I2S_BCK / I2S_LRCK / I2S_DIN
# Falls back to [VISUAL ONLY] if DAC not connected

import displayio
import terminalio
import vectorio
import time
import gc
import math
import array
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

# ── Notes ─────────────────────────────────────────────────────────────────────
NOTE_NAMES = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
NOTE_FREQS = [262,  294,  330,  349,  392,  440,  494,  523]

# ── Hex geometry (flat-topped, circumradius 28/24) ────────────────────────────
_HEX_OUTER = [(0,-28),(24,-14),(24,14),(0,28),(-24,14),(-24,-14)]
_HEX_INNER = [(0,-24),(21,-12),(21,12),(0,24),(-21,12),(-21,-12)]

# 3-2-3 honeycomb positions (cx, cy)
# Column spacing 54px, row spacing 48px, centred at x=120
# Row 0 (3): y=162, x=66/120/174
# Row 1 (2): y=210, x=93/147   (offset +27 for honeycomb interlock)
# Row 2 (3): y=258, x=66/120/174
_HEX_POS = [
    ( 66, 162),   # C4
    (120, 162),   # D4
    (174, 162),   # E4
    ( 93, 210),   # F4
    (147, 210),   # G4
    ( 66, 258),   # A4
    (120, 258),   # B4
    (174, 258),   # C5
]
_KEY_Y_MIN = 134   # 162 - 28
_KEY_Y_MAX = 286   # 258 + 28

# ── Oscilloscope bar layout ───────────────────────────────────────────────────
_BAR_COUNT  = 8
_BAR_W      = 20
_BAR_GAP    = 8
_BAR_X0     = (240 - (_BAR_COUNT * _BAR_W + (_BAR_COUNT - 1) * _BAR_GAP)) // 2  # 14
_BAR_BOT_Y  = 60
_BAR_H_MAX  = 36
_BAR_H_IDLE = 4

# ── Static Y values ───────────────────────────────────────────────────────────
_SEP1_Y    = 64
_STAT_CY   = 76
_SEP2_Y    = 88
_NOTEHZ_CY = 104   # combined "C4  262 Hz" line (scale=2)
_SEP3_Y    = 118

# ── Audio helpers ─────────────────────────────────────────────────────────────
SAMPLE_RATE = 8000

def _make_tone(freq):
    length = max(1, SAMPLE_RATE // freq)
    buf = array.array("H", [0] * length)
    for i in range(length):
        buf[i] = int(32767 * math.sin(2 * math.pi * i / length) + 32768)
    import audiocore
    return audiocore.RawSample(buf, sample_rate=SAMPLE_RATE)


# ── Nearest-hex hit detection ─────────────────────────────────────────────────
def _find_hex(tx, ty):
    if ty < _KEY_Y_MIN or ty > _KEY_Y_MAX:
        return -1
    best    = -1
    best_d2 = 999999
    for i, (cx, cy) in enumerate(_HEX_POS):
        d2 = (tx - cx) ** 2 + (ty - cy) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best    = i
    return best


# ── App entry point ───────────────────────────────────────────────────────────
def run(display, touch, W, H):

    # Audio init
    _audio  = None
    HAS_AUD = False
    try:
        import audiobusio, board
        _audio  = audiobusio.I2SOut(board.I2S_BCK, board.I2S_LRCK, board.I2S_DIN)
        HAS_AUD = True
    except Exception:
        pass

    NOTE_SAMPLES = None
    if HAS_AUD:
        try:
            NOTE_SAMPLES = [_make_tone(f) for f in NOTE_FREQS]
        except Exception:
            HAS_AUD = False

    try:
        _run_synth(display, touch, W, H, _audio, HAS_AUD, NOTE_SAMPLES)
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


def _run_synth(display, touch, W, H, _audio, HAS_AUD, NOTE_SAMPLES):

    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:MINI SYNTH", "v2.0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # ── Oscilloscope bars ─────────────────────────────────────────────────
    bar_pals  = []
    bar_rects = []
    for i in range(_BAR_COUNT):
        bx  = _BAR_X0 + i * (_BAR_W + _BAR_GAP)
        pal = displayio.Palette(1)
        pal[0] = ui.C_GREEN_DIM
        r = vectorio.Rectangle(pixel_shader=pal,
                               x=bx, y=_BAR_BOT_Y - _BAR_H_IDLE,
                               width=_BAR_W, height=_BAR_H_IDLE)
        scene.append(r)
        bar_pals.append(pal)
        bar_rects.append(r)

    ui.solid_rect(scene, 0, _SEP1_Y, W, 1, ui.C_GREEN_DIM)

    # ── Audio status ──────────────────────────────────────────────────────
    stat_lbl = label.Label(terminalio.FONT,
                           text="[AUDIO OK]" if HAS_AUD else "[VISUAL ONLY]",
                           color=ui.C_GREEN_HI if HAS_AUD else ui.C_AMBER,
                           scale=1)
    stat_lbl.anchor_point    = (0.5, 0.5)
    stat_lbl.anchored_position = (W // 2, _STAT_CY)
    scene.append(stat_lbl)

    ui.solid_rect(scene, 0, _SEP2_Y, W, 1, ui.C_GREEN_DIM)

    # ── Note + frequency (single line) ───────────────────────────────────
    notehz_lbl = label.Label(terminalio.FONT, text="--  --- Hz",
                             color=ui.C_GREEN_HI, scale=2)
    notehz_lbl.anchor_point    = (0.5, 0.5)
    notehz_lbl.anchored_position = (W // 2, _NOTEHZ_CY)
    scene.append(notehz_lbl)

    ui.solid_rect(scene, 0, _SEP3_Y, W, 1, ui.C_GREEN_DIM)

    # ── Honeycomb hexagons ────────────────────────────────────────────────
    hex_fill_pals   = []
    hex_border_pals = []
    hex_note_lbls   = []

    for i, (cx, cy) in enumerate(_HEX_POS):
        # Border layer (outer hex, dim colour)
        bpal    = displayio.Palette(1)
        bpal[0] = ui.C_GREEN_DIM
        scene.append(vectorio.Polygon(pixel_shader=bpal,
                                      points=list(_HEX_OUTER), x=cx, y=cy))
        hex_border_pals.append(bpal)

        # Fill layer (inner hex, palette updated on press)
        fpal    = displayio.Palette(1)
        fpal[0] = ui.C_BG_PANEL
        scene.append(vectorio.Polygon(pixel_shader=fpal,
                                      points=list(_HEX_INNER), x=cx, y=cy))
        hex_fill_pals.append(fpal)

        # Note label
        nl = label.Label(terminalio.FONT, text=NOTE_NAMES[i],
                         color=ui.C_GREEN_DIM, scale=1)
        nl.anchor_point    = (0.5, 0.5)
        nl.anchored_position = (cx, cy)
        scene.append(nl)
        hex_note_lbls.append(nl)

    ui.make_footer(scene, "TOUCH KEYS   ^ SWIPE UP to quit")
    display.root_group = scene

    # ── Bar animation state ───────────────────────────────────────────────
    bar_heights = [_BAR_H_IDLE] * _BAR_COUNT
    bar_targets = [_BAR_H_IDLE] * _BAR_COUNT

    def _update_bars():
        for i in range(_BAR_COUNT):
            h = bar_heights[i]
            t = bar_targets[i]
            if h == t:
                continue
            step = max(1, abs(t - h) // 2)
            if t > h:
                h = min(h + step, t)
            else:
                h = max(h - step, t)
            bar_heights[i]      = h
            bar_rects[i].y      = _BAR_BOT_Y - h
            bar_rects[i].height = h

    # ── Key press / release ───────────────────────────────────────────────
    active_key = -1

    def _key_press(k):
        nonlocal active_key
        if k == active_key:
            return
        if active_key >= 0:
            _key_release(active_key)
        active_key             = k
        hex_fill_pals[k][0]   = ui.C_GREEN_MID
        hex_border_pals[k][0] = ui.C_GREEN_HI
        hex_note_lbls[k].color = ui.C_GREEN_HI
        notehz_lbl.text        = "{}  {} Hz".format(NOTE_NAMES[k], NOTE_FREQS[k])
        bar_targets[k]         = _BAR_H_MAX
        bar_pals[k][0]         = ui.C_GREEN_HI
        if HAS_AUD and NOTE_SAMPLES:
            try:
                _audio.stop()
                _audio.play(NOTE_SAMPLES[k], loop=True)
            except Exception:
                pass

    def _key_release(k):
        nonlocal active_key
        if k < 0:
            return
        hex_fill_pals[k][0]   = ui.C_BG_PANEL
        hex_border_pals[k][0] = ui.C_GREEN_DIM
        hex_note_lbls[k].color = ui.C_GREEN_DIM
        bar_targets[k]         = _BAR_H_IDLE
        bar_pals[k][0]         = ui.C_GREEN_DIM
        if k == active_key:
            active_key = -1
        if HAS_AUD:
            try:
                _audio.stop()
            except Exception:
                pass

    # ── Main event loop ───────────────────────────────────────────────────
    fd       = False
    sx = sy  = 0
    lx = ly  = 0
    last_hex = -1

    while True:
        x, y, tch = touch.read()
        _update_bars()
        time.sleep(0.03)

        if tch:
            lx, ly = x, y
            if not fd:
                fd     = True
                sx, sy = x, y

            # Track hex under finger continuously
            k = _find_hex(x, y)
            if k != last_hex:
                if last_hex >= 0:
                    _key_release(last_hex)
                if k >= 0:
                    _key_press(k)
                last_hex = k

        elif fd:
            fd = False
            if last_hex >= 0:
                _key_release(last_hex)
                last_hex = -1

            g = classify_gesture(sx, sy, lx, ly, W, H,
                                 swipe_edge=ui.SWIPE_EDGE,
                                 swipe_min_dist=ui.SWIPE_MIN)
            if g and g[0] == "SWIPE UP":
                break
