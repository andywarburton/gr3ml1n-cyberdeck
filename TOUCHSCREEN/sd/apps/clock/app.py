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
import rtc as _rtc
import gc
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

_DAYS   = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
           "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


# ── Time source helpers ───────────────────────────────────────────────────────

def _get_tz():
    """Read TZ_OFFSET (integer hours) from settings.toml, default 0."""
    try:
        import os
        return int(os.getenv("TZ_OFFSET") or "0")
    except Exception:
        return 0


def _try_external_rtc():
    """
    Scan I2C for common RTC modules and sync the internal RTC from the first
    one found.  Returns a short name string, or None if not found.
    """
    try:
        import busio
        import board
        i2c = busio.I2C(board.SCL, board.SDA)
        while not i2c.try_lock():
            pass
        addrs = i2c.scan()
        i2c.unlock()

        if 0x68 in addrs:
            # DS3231 (also handles DS1307 at same address)
            try:
                import adafruit_ds3231
                ext = adafruit_ds3231.DS3231(i2c)
                _rtc.RTC().datetime = ext.datetime
                i2c.deinit()
                return "DS3231"
            except Exception:
                pass
            # PCF8523
            try:
                import adafruit_pcf8523
                ext = adafruit_pcf8523.PCF8523(i2c)
                _rtc.RTC().datetime = ext.datetime
                i2c.deinit()
                return "PCF8523"
            except Exception:
                pass

        if 0x51 in addrs:
            try:
                import adafruit_pcf8563
                ext = adafruit_pcf8563.PCF8563(i2c)
                _rtc.RTC().datetime = ext.datetime
                i2c.deinit()
                return "PCF8563"
            except Exception:
                pass

        i2c.deinit()
    except Exception as e:
        # "in use" means SCL/SDA are shared with the touch driver — not an error
        if "in use" not in str(e).lower():
            print("clock: RTC probe:", e)
    return None


def _unix_to_struct_time(unix_secs):
    """
    Convert a Unix timestamp (seconds since Jan 1 1970) to a struct_time.
    Computed entirely in integer arithmetic — avoids platform time_t limits
    and epoch differences between CircuitPython ports.
    """
    _MDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def _leap(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

    s    = int(unix_secs)
    sec  = s % 60;  s //= 60
    min_ = s % 60;  s //= 60
    hour = s % 24;  s //= 24
    # s = whole days since 1970-01-01 (which was a Thursday)
    wday = (s + 3) % 7          # 0=Mon … 6=Sun

    year = 1970
    while True:
        ylen = 366 if _leap(year) else 365
        if s < ylen:
            break
        s -= ylen
        year += 1

    yday = s + 1
    mon  = 1
    for m in range(12):
        mlen = _MDays[m] + (1 if m == 1 and _leap(year) else 0)
        if s < mlen:
            break
        s -= mlen
        mon += 1

    return time.struct_time((year, mon, s + 1, hour, min_, sec, wday, yday, -1))


def _eu_dst(year, month, mday, utc_hour):
    """
    Return True if European Summer Time (CEST) is active for the given UTC time.

    Rules (EU directive):
      DST begins: last Sunday of March    at 01:00 UTC  (clocks → UTC+2)
      DST ends:   last Sunday of October  at 01:00 UTC  (clocks → UTC+1)
    """
    if month < 3 or month > 10:
        return False          # Jan, Feb, Nov, Dec → always standard time
    if 3 < month < 10:
        return True           # Apr – Sep → always summer time

    def _last_sun(y, m):
        # Sakamoto's weekday algorithm: returns 0=Sun, 1=Mon … 6=Sat
        t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
        mlen = [31, 29 if (y%4==0 and (y%100!=0 or y%400==0)) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        d = mlen[m - 1]
        while True:
            yy = y - (1 if m < 3 else 0)
            if (yy + yy//4 - yy//100 + yy//400 + t[m-1] + d) % 7 == 0:
                return d
            d -= 1

    ls = _last_sun(year, month)

    if month == 3:   # spring forward: DST starts at last-Sun 01:00 UTC
        if mday < ls: return False
        if mday > ls: return True
        return utc_hour >= 1

    else:            # month == 10: fall back: DST ends at last-Sun 01:00 UTC
        if mday < ls: return True
        if mday > ls: return False
        return utc_hour < 1


def _try_ntp(tz_base):
    """
    Fetch time from pool.ntp.org using a raw UDP socket — no adafruit_ntp needed.
    Applies European DST automatically on top of tz_base (standard UTC offset).
    Returns a display label string on success (e.g. 'CEST UTC+2'), None on failure.
    """
    try:
        import wifi, socketpool, struct, os

        ssid = os.getenv("CIRCUITPY_WIFI_SSID")
        pwd  = os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""
        if not ssid:
            return None
        if not wifi.radio.ipv4_address:
            wifi.radio.connect(ssid, pwd)

        pool   = socketpool.SocketPool(wifi.radio)
        packet = bytearray(48)
        packet[0] = 0x1B          # LI=0, Version=3, Mode=3 (client)

        addr = pool.getaddrinfo("pool.ntp.org", 123)[0][-1]
        sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
        try:
            sock.settimeout(5)
            sock.sendto(packet, addr)
            resp = bytearray(48)
            n    = sock.recv_into(resp)
        finally:
            sock.close()

        if n < 48:
            raise Exception("short response ({} bytes)".format(n))

        # Transmit timestamp: unsigned 32-bit big-endian at byte offset 40
        # = seconds since Jan 1 1900.
        ntp_secs = struct.unpack_from("!I", resp, 40)[0]
        if ntp_secs < 3786825600:   # sanity: must be after Jan 1 2020
            raise Exception("implausible timestamp: {}".format(ntp_secs))

        unix_utc = ntp_secs - 2208988800   # → Unix UTC seconds

        # Determine DST from the UTC time, then build local time
        t_utc  = _unix_to_struct_time(unix_utc)
        dst    = _eu_dst(t_utc.tm_year, t_utc.tm_mon, t_utc.tm_mday, t_utc.tm_hour)
        offset = tz_base + (1 if dst else 0)

        _rtc.RTC().datetime = _unix_to_struct_time(unix_utc + offset * 3600)

        name = "CEST" if dst else "CET"
        return "{} UTC+{}".format(name, offset)
    except Exception as e:
        print("clock: NTP:", e)
        return None


def _set_fallback():
    """Set internal RTC to 13:13:00 so time.localtime() works consistently."""
    try:
        # struct_time: (year, month, mday, hour, min, sec, wday, yday, dst)
        _rtc.RTC().datetime = time.struct_time((2025, 1, 1, 13, 13, 0, 2, 1, -1))
    except Exception:
        pass


# ── Status / detection splash ─────────────────────────────────────────────────

def _detection_splash(display, W, H, msg):
    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:CLOCK", "v1.0")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)
    lbl = label.Label(terminalio.FONT, text=msg,
                      color=ui.C_GREEN_DIM, scale=1)
    lbl.anchor_point = (0.5, 0.5)
    lbl.anchored_position = (W // 2, H // 2)
    sc.append(lbl)
    display.root_group = sc
    return sc


# ── App entry point ───────────────────────────────────────────────────────────

def run(display, touch, keyboard, W, H):

    # ── Detect time source (with live status splash) ──────────────────────
    splash = _detection_splash(display, W, H, "SCANNING I2C FOR RTC...")
    rtc_name = _try_external_rtc()
    display.root_group = displayio.Group()
    del splash; gc.collect()

    tz = _get_tz()

    if rtc_name:
        source  = "RTC: " + rtc_name
        src_col = ui.C_GREEN_HI
    else:
        splash = _detection_splash(display, W, H, "CONNECTING TO NTP...")
        ntp_label = _try_ntp(tz)
        display.root_group = displayio.Group()
        del splash; gc.collect()

        if ntp_label:
            source  = "NTP " + ntp_label
            src_col = ui.C_GREEN_HI
        else:
            _set_fallback()
            source  = "FALLBACK 13:13"
            src_col = ui.C_AMBER

    # ── Build clock scene ─────────────────────────────────────────────────
    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:CLOCK", "v1.0")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    # Source badge
    src_lbl = label.Label(terminalio.FONT,
                          text="SOURCE: " + source,
                          color=src_col, scale=1)
    src_lbl.anchor_point = (0.5, 0.5)
    src_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 12)
    sc.append(src_lbl)
    ui.solid_rect(sc, 4, ui.CONTENT_Y + 22, W - 8, 1, ui.C_GREEN_DIM)

    # Decorative border framing the clock face
    ui.make_border(sc, 10, 58, W - 20, 138, ui.C_GREEN_DIM)

    # ── HH : MM  at scale=4 ───────────────────────────────────────────────
    # scale=4 font: 24px wide × 32px tall per character
    # "HH" + ":" + "MM" = 48 + 24 + 48 = 120px → left edge at (240-120)/2 = 60
    # Rendered as three separate labels so the colon can blink independently.
    TIME_CY = 120   # vertical centre of HH:MM

    h_lbl = label.Label(terminalio.FONT, text="--",
                        color=ui.C_GREEN_HI, scale=4)
    h_lbl.anchor_point    = (1.0, 0.5)
    h_lbl.anchored_position = (W // 2 - 12, TIME_CY)   # 12 = half colon width
    sc.append(h_lbl)

    colon_lbl = label.Label(terminalio.FONT, text=":",
                            color=ui.C_GREEN_HI, scale=4)
    colon_lbl.anchor_point    = (0.5, 0.5)
    colon_lbl.anchored_position = (W // 2, TIME_CY)
    sc.append(colon_lbl)

    m_lbl = label.Label(terminalio.FONT, text="--",
                        color=ui.C_GREEN_HI, scale=4)
    m_lbl.anchor_point    = (0.0, 0.5)
    m_lbl.anchored_position = (W // 2 + 12, TIME_CY)
    sc.append(m_lbl)

    # ── Seconds at scale=2 ────────────────────────────────────────────────
    sec_lbl = label.Label(terminalio.FONT, text=":--",
                          color=ui.C_GREEN_MID, scale=2)
    sec_lbl.anchor_point    = (0.5, 0.5)
    sec_lbl.anchored_position = (W // 2, TIME_CY + 36)   # 36 = 32/2 + 20
    sc.append(sec_lbl)

    # ── Date ──────────────────────────────────────────────────────────────
    ui.solid_rect(sc, 20, 208, W - 40, 1, ui.C_GREEN_DIM)

    date_lbl = label.Label(terminalio.FONT, text="--- -- --- ----",
                           color=ui.C_GREEN, scale=2)
    date_lbl.anchor_point    = (0.5, 0.5)
    date_lbl.anchored_position = (W // 2, 230)
    sc.append(date_lbl)

    day_lbl = label.Label(terminalio.FONT, text="---------",
                          color=ui.C_GREEN_DIM, scale=1)
    day_lbl.anchor_point    = (0.5, 0.5)
    day_lbl.anchored_position = (W // 2, 252)
    sc.append(day_lbl)

    ui.make_footer(sc, "ESC or SWIPE UP to quit")
    display.root_group = sc

    # ── Event loop ────────────────────────────────────────────────────────
    _DAYS_FULL = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                  "FRIDAY", "SATURDAY", "SUNDAY"]

    last_sec = -1
    fd = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        t = time.localtime()

        if t.tm_sec != last_sec:
            first = (last_sec == -1)
            last_sec = t.tm_sec

            h_lbl.text = "{:02d}".format(t.tm_hour)
            m_lbl.text = "{:02d}".format(t.tm_min)
            sec_lbl.text = ":{:02d}".format(t.tm_sec)

            # Blink colon: on for even seconds, off (bg colour) for odd
            colon_lbl.color = (ui.C_GREEN_HI if t.tm_sec % 2 == 0
                               else ui.C_BG)

            # Date only changes at midnight (or on first render)
            if first or t.tm_sec == 0:
                wd  = t.tm_wday % 7
                mon = (t.tm_mon - 1) % 12
                date_lbl.text = "{} {:02d} {} {:04d}".format(
                    _DAYS[wd], t.tm_mday, _MONTHS[mon], t.tm_year)
                day_lbl.text = _DAYS_FULL[wd]

        x, y, tch = touch.read()
        time.sleep(0.05)

        if tch:
            lx, ly = x, y
            if not fd:
                fd = True
                sx, sy = x, y
        elif fd:
            fd = False
            g = classify_gesture(sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
            if g and g[0] == "SWIPE UP":
                break

    display.root_group = displayio.Group()
    del sc
    gc.collect()
