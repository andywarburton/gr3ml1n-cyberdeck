# apps/clock/app.py
# CyberDeck app: Digital Clock | portrait 240x320
#
# Time source priority:
#   1. External I2C RTC  (DS3231 / PCF8523 / PCF8563)
#   2. NTP via WiFi      (needs CIRCUITPY_WIFI_SSID + CIRCUITPY_WIFI_PASSWORD
#                         in settings.toml; optional TZ_OFFSET for UTC offset)
#   3. Fallback          (starts at 13:13:00, counts up from there)

import displayio
import terminalio
import time
import gc
import math
import array
from adafruit_display_text import label
from waveshare_touch import classify_gesture
from battery_monitor import BatteryMonitor
import timekeeper
import cyber_ui as ui

_DAYS   = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


# ── Audio helper ──────────────────────────────────────────────────────────────

SAMPLE_RATE = 8000

def _make_beep(freq=1000):
    length = max(1, SAMPLE_RATE // freq)
    buf = array.array("H", [0] * length)
    for i in range(length):
        buf[i] = int(32767 * math.sin(2 * math.pi * i / length) + 32768)
    import audiocore
    return audiocore.RawSample(buf, sample_rate=SAMPLE_RATE)


# ── Status / detection splash ─────────────────────────────────────────────────

def _detection_splash(display, W, H, msg, battery_str=""):
    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:CLOCK", battery_str=battery_str)
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)
    lbl = label.Label(terminalio.FONT, text=msg,
                      color=ui.C_GREEN_DIM, scale=1)
    lbl.anchor_point = (0.5, 0.5)
    lbl.anchored_position = (W // 2, H // 2)
    sc.append(lbl)
    display.root_group = sc
    return sc


# ── App entry point ───────────────────────────────────────────────────────────

def _fmt_battery(batt):
    v = batt.voltage
    if v > 0.1:
        return "{:.1f}V".format(v)
    return ""


def run(display, touch, keyboard, W, H):
    batt = BatteryMonitor()
    bat_str = _fmt_battery(batt)

    # ── Detect time source (with live status splash) ──────────────────────
    splash = _detection_splash(display, W, H, "SYNCING TIME...",
                               battery_str=bat_str)
    timekeeper.sync()
    display.root_group = displayio.Group()
    del splash; gc.collect()

    source = timekeeper.source_name
    if source.startswith("RTC") or source.startswith("NTP"):
        src_col = ui.C_GREEN_HI
    else:
        src_col = ui.C_AMBER

    # ── Build clock scene ─────────────────────────────────────────────────
    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:CLOCK", battery_str=_fmt_battery(batt))
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    # Source badge
    src_lbl = label.Label(terminalio.FONT,
                          text="SOURCE: " + source,
                          color=src_col, scale=1)
    src_lbl.anchor_point = (0.5, 0.5)
    src_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 12)
    sc.append(src_lbl)
    ui.solid_rect(sc, 4, ui.CONTENT_Y + 22, W - 8, 1, ui.C_GREEN_DIM)

    # ── HH : MM : SS  at scale=4 ──────────────────────────────────────────
    # scale=4 font: 24px wide × 32px tall per character
    # "HH:MM:SS" = 8 chars × 24 = 192px → left edge at (240-192)/2 = 24
    TIME_CY = 70

    h_lbl = label.Label(terminalio.FONT, text="--",
                        color=ui.C_GREEN_HI, scale=4)
    h_lbl.anchor_point    = (0.0, 0.5)
    h_lbl.anchored_position = (24, TIME_CY)
    sc.append(h_lbl)

    colon_lbl = label.Label(terminalio.FONT, text=":",
                            color=ui.C_GREEN_HI, scale=4)
    colon_lbl.anchor_point    = (0.0, 0.5)
    colon_lbl.anchored_position = (72, TIME_CY)
    sc.append(colon_lbl)

    m_lbl = label.Label(terminalio.FONT, text="--",
                        color=ui.C_GREEN_HI, scale=4)
    m_lbl.anchor_point    = (0.0, 0.5)
    m_lbl.anchored_position = (96, TIME_CY)
    sc.append(m_lbl)

    colon2_lbl = label.Label(terminalio.FONT, text=":",
                             color=ui.C_GREEN_HI, scale=4)
    colon2_lbl.anchor_point    = (0.0, 0.5)
    colon2_lbl.anchored_position = (144, TIME_CY)
    sc.append(colon2_lbl)

    sec_lbl = label.Label(terminalio.FONT, text="--",
                          color=ui.C_GREEN_HI, scale=4)
    sec_lbl.anchor_point    = (0.0, 0.5)
    sec_lbl.anchored_position = (168, TIME_CY)
    sc.append(sec_lbl)

    # ── Date ──────────────────────────────────────────────────────────────
    date_lbl = label.Label(terminalio.FONT, text="--- -- --- ----",
                           color=ui.C_GREEN, scale=2)
    date_lbl.anchor_point    = (0.5, 0.5)
    date_lbl.anchored_position = (W // 2, 115)
    sc.append(date_lbl)

    # ── Alarm ─────────────────────────────────────────────────────────────
    alarm_lbl = label.Label(terminalio.FONT, text="ALARM: --:--",
                            color=ui.C_GREEN_DIM, scale=2)
    alarm_lbl.anchor_point    = (0.5, 0.5)
    alarm_lbl.anchored_position = (W // 2, 275)
    sc.append(alarm_lbl)

    # Focus underline (visible only when editing alarm)
    import vectorio
    _focus_pal = displayio.Palette(1)
    _focus_pal[0] = ui.C_BG
    _focus_rect = vectorio.Rectangle(pixel_shader=_focus_pal,
                                      x=W // 2 - 60, y=288,
                                      width=120, height=3)
    sc.append(_focus_rect)

    # Full-screen flash overlay (behind text labels, drawn on top of bg)
    _flash_pal = displayio.Palette(1)
    _flash_pal[0] = ui.C_BG
    _flash_rect = vectorio.Rectangle(pixel_shader=_flash_pal,
                                      x=0, y=0, width=W, height=H)
    sc.insert(2, _flash_rect)

    ui.make_footer(sc, "ESC or SWIPE UP to quit")
    display.root_group = sc

    # Audio init for alarm
    _audio = None
    HAS_AUD = False
    try:
        import audiobusio, board
        _audio = audiobusio.I2SOut(board.I2S_BCK, board.I2S_LRCK, board.I2S_DIN)
        HAS_AUD = True
    except Exception:
        pass

    beep_sample = None
    if HAS_AUD:
        try:
            beep_sample = _make_beep(1500)
        except Exception:
            HAS_AUD = False

    # Alarm state
    alarm_digits = []
    alarm_hour = None
    alarm_min = None
    alarm_set = False
    alarm_ringing = False
    alarm_beep_counter = 0
    alarm_sound_on = False
    last_triggered_at = None

    def _pad_digits(digits, width=4, fill="_"):
        out = "".join(digits)
        while len(out) < width:
            out += fill
        return out

    def _update_alarm_display():
        if alarm_set:
            alarm_lbl.text = "ALARM: {:02d}:{:02d}".format(alarm_hour, alarm_min)
            alarm_lbl.color = ui.C_GREEN_HI
            _focus_pal[0] = ui.C_BG
        elif len(alarm_digits) == 4:
            alarm_lbl.text = "ALARM: INVALID"
            alarm_lbl.color = ui.C_AMBER
            _focus_pal[0] = ui.C_BG
        elif len(alarm_digits) == 0:
            alarm_lbl.text = "ALARM: --:--"
            alarm_lbl.color = ui.C_GREEN_DIM
            _focus_pal[0] = ui.C_BG
        else:
            d = _pad_digits(alarm_digits)
            alarm_lbl.text = "ALARM: {}:{}".format(d[:2], d[2:])
            alarm_lbl.color = ui.C_GREEN_MID
            _focus_pal[0] = ui.C_AMBER

    # ── Event loop ────────────────────────────────────────────────────────
    last_sec = -1
    fd = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()

            # Alarm cancellation takes priority
            if alarm_ringing and kbd['escape']:
                alarm_ringing = False
                alarm_beep_counter = 0
                _flash_pal[0] = ui.C_BG
                if alarm_sound_on:
                    if HAS_AUD:
                        try:
                            _audio.stop()
                        except Exception:
                            pass
                    alarm_sound_on = False
                _update_alarm_display()
                print("clock: alarm cancelled")
                continue

            if not alarm_ringing:
                if kbd['escape']:
                    break

                # Alarm input
                if kbd['char'] is not None and kbd['char'] in "0123456789":
                    if len(alarm_digits) < 4:
                        alarm_digits.append(kbd['char'])
                        if len(alarm_digits) == 4:
                            hh = int(alarm_digits[0] + alarm_digits[1])
                            mm = int(alarm_digits[2] + alarm_digits[3])
                            if 0 <= hh <= 23 and 0 <= mm <= 59:
                                alarm_hour = hh
                                alarm_min = mm
                                alarm_set = True
                                alarm_digits = []
                                print("clock: alarm set to {:02d}:{:02d}".format(hh, mm))
                            else:
                                print("clock: invalid alarm time")
                        _update_alarm_display()

                if kbd['delete']:
                    if alarm_set:
                        alarm_set = False
                        alarm_hour = None
                        alarm_min = None
                        alarm_digits = []
                        last_triggered_at = None
                        print("clock: alarm cleared")
                    elif alarm_digits:
                        alarm_digits.pop()
                        print("clock: alarm digit removed")
                    _update_alarm_display()

        t = time.localtime()

        if t.tm_sec != last_sec:
            first = (last_sec == -1)
            last_sec = t.tm_sec

            h_lbl.text = "{:02d}".format(t.tm_hour)
            m_lbl.text = "{:02d}".format(t.tm_min)
            sec_lbl.text = "{:02d}".format(t.tm_sec)

            # Date only changes at midnight (or on first render)
            if first or t.tm_sec == 0:
                wd  = t.tm_wday % 7
                mon = (t.tm_mon - 1) % 12
                date_lbl.text = "{} {:02d} {} {:04d}".format(
                    _DAYS[wd], t.tm_mday, _MONTHS[mon], t.tm_year)

            # Alarm trigger check
            if alarm_set and not alarm_ringing:
                now = (t.tm_yday, t.tm_hour, t.tm_min)
                if now != last_triggered_at:
                    if t.tm_hour == alarm_hour and t.tm_min == alarm_min:
                        last_triggered_at = now
                        alarm_ringing = True
                        alarm_beep_counter = 0
                        print("clock: ALARM TRIGGERED")

        # 80s alarm: 4 beeps (0.4s on / 0.3s off), 1.2s pause, repeat
        if alarm_ringing:
            alarm_beep_counter += 1
            if alarm_beep_counter >= 74:
                alarm_beep_counter = 0
            # beep ticks: 0-7, 14-21, 28-35, 42-49
            should_play = alarm_beep_counter in (
                0, 1, 2, 3, 4, 5, 6, 7,
                14, 15, 16, 17, 18, 19, 20, 21,
                28, 29, 30, 31, 32, 33, 34, 35,
                42, 43, 44, 45, 46, 47, 48, 49,
            )

            # Flash whole screen amber during each beep
            _flash_pal[0] = ui.C_AMBER if should_play else ui.C_BG
            alarm_lbl.color = ui.C_GREEN_HI if should_play else ui.C_BG

            if should_play and not alarm_sound_on:
                if HAS_AUD and beep_sample:
                    try:
                        _audio.play(beep_sample, loop=True)
                    except Exception:
                        pass
                alarm_sound_on = True
            elif not should_play and alarm_sound_on:
                if HAS_AUD:
                    try:
                        _audio.stop()
                    except Exception:
                        pass
                alarm_sound_on = False

        x, y, tch = touch.read()
        time.sleep(0.05)

        if tch:
            lx, ly = x, y
            if not fd:
                fd = True
                sx, sy = x, y
        elif fd:
            fd = False
            if alarm_ringing:
                alarm_ringing = False
                alarm_beep_counter = 0
                _flash_pal[0] = ui.C_BG
                if alarm_sound_on:
                    if HAS_AUD:
                        try:
                            _audio.stop()
                        except Exception:
                            pass
                    alarm_sound_on = False
                _update_alarm_display()
                print("clock: alarm cancelled by touch")
            else:
                g = classify_gesture(sx, sy, lx, ly, W, H,
                    swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
                if g and g[0] == "SWIPE UP":
                    break
                # Tap on time area = test alarm (small movement, no gesture)
                dx = abs(lx - sx)
                dy = abs(ly - sy)
                if dx < 10 and dy < 10 and 38 < ly < 102:
                    alarm_ringing = True
                    alarm_beep_counter = 0
                    print("clock: alarm test triggered")

    display.root_group = displayio.Group()
    if _audio:
        try:
            _audio.stop()
        except Exception:
            pass
        try:
            _audio.deinit()
        except Exception:
            pass
    del sc
    gc.collect()
