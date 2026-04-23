# apps/battery_timer/app.py
# CyberDeck app: Battery Timer | portrait 240x320
# Logs time + runtime every minute. Start wipes the log file.

import displayio
import terminalio
import time
import rtc as _rtc
import gc
import os
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

_LOG_FILE = "/sd/apps/battery_timer/log.txt"

# ── File helpers ─────────────────────────────────────────────────────────────-

def _file_size(path):
    try:
        return os.stat(path)[6]
    except OSError:
        return -1


def _read_log():
    try:
        with open(_LOG_FILE) as fh:
            return fh.read()
    except OSError:
        return ""


# ── Time source helpers (from clock app) ─────────────────────────────────-----

def _get_tz():
    try:
        return int(os.getenv("TZ_OFFSET") or "0")
    except Exception:
        return 0


def _unix_to_struct_time(unix_secs):
    _MDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def _leap(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

    s = int(unix_secs)
    sec = s % 60;  s //= 60
    min_ = s % 60;  s //= 60
    hour = s % 24;  s //= 24
    wday = (s + 3) % 7
    year = 1970
    while True:
        ylen = 366 if _leap(year) else 365
        if s < ylen:
            break
        s -= ylen
        year += 1
    yday = s + 1
    mon = 1
    for m in range(12):
        mlen = _MDays[m] + (1 if m == 1 and _leap(year) else 0)
        if s < mlen:
            break
        s -= mlen
        mon += 1
    return time.struct_time((year, mon, s + 1, hour, min_, sec, wday, yday, -1))


def _eu_dst(year, month, mday, utc_hour):
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True

    def _last_sun(y, m):
        t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
        mlen = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        d = mlen[m - 1]
        while True:
            yy = y - (1 if m < 3 else 0)
            if (yy + yy // 4 - yy // 100 + yy // 400 + t[m - 1] + d) % 7 == 0:
                return d
            d -= 1

    ls = _last_sun(year, month)
    if month == 3:
        if mday < ls:
            return False
        if mday > ls:
            return True
        return utc_hour >= 1
    else:
        if mday < ls:
            return True
        if mday > ls:
            return False
        return utc_hour < 1


def _try_ntp(tz_base):
    try:
        import wifi, socketpool, struct, os
        ssid = os.getenv("CIRCUITPY_WIFI_SSID")
        pwd = os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""
        if not ssid:
            return None
        if not wifi.radio.ipv4_address:
            wifi.radio.connect(ssid, pwd)
        pool = socketpool.SocketPool(wifi.radio)
        packet = bytearray(48)
        packet[0] = 0x1B
        addr = pool.getaddrinfo("pool.ntp.org", 123)[0][-1]
        sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
        try:
            sock.settimeout(5)
            sock.sendto(packet, addr)
            resp = bytearray(48)
            n = sock.recv_into(resp)
        finally:
            sock.close()
        if n < 48:
            raise Exception("short response")
        ntp_secs = struct.unpack_from("!I", resp, 40)[0]
        if ntp_secs < 3786825600:
            raise Exception("implausible timestamp")
        unix_utc = ntp_secs - 2208988800
        t_utc = _unix_to_struct_time(unix_utc)
        dst = _eu_dst(t_utc.tm_year, t_utc.tm_mon, t_utc.tm_mday, t_utc.tm_hour)
        offset = tz_base + (1 if dst else 0)
        _rtc.RTC().datetime = _unix_to_struct_time(unix_utc + offset * 3600)
        name = "CEST" if dst else "CET"
        return "{} UTC+{}".format(name, offset)
    except Exception as e:
        print("battery_timer: NTP:", e)
        return None


def _try_external_rtc():
    try:
        import busio
        import board
        i2c = busio.I2C(board.SCL, board.SDA)
        while not i2c.try_lock():
            pass
        addrs = i2c.scan()
        i2c.unlock()

        if 0x68 in addrs:
            try:
                import adafruit_ds3231
                ext = adafruit_ds3231.DS3231(i2c)
                _rtc.RTC().datetime = ext.datetime
                i2c.deinit()
                return "DS3231"
            except Exception:
                pass
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
        if "in use" not in str(e).lower():
            print("battery_timer: RTC probe:", e)
    return None


def _set_fallback():
    try:
        _rtc.RTC().datetime = time.struct_time((2025, 1, 1, 13, 13, 0, 2, 1, -1))
    except Exception:
        pass


# ── Display helpers ─────────────────────────────────────────────────----------

def _format_runtime(total_seconds):
    m = total_seconds // 60
    s = total_seconds % 60
    if m < 60:
        return "{:02d}:{:02d}".format(m, s)
    h = m // 60
    m = m % 60
    return "{:02d}:{:02d}:{:02d}".format(h, m, s)


def _make_tally(minutes):
    if minutes <= 0:
        return ""
    groups = []
    full = minutes // 5
    rem = minutes % 5
    for _ in range(full):
        groups.append("|||||")
    if rem:
        groups.append("|" * rem)
    s = " ".join(groups)
    if len(s) > 38:
        s = s[:35] + "..."
    return s


def _wrap_lines(text, max_chars=28):
    lines = text.split("\n")
    out = []
    for line in lines:
        while len(line) > max_chars:
            out.append(line[:max_chars])
            line = line[max_chars:]
        out.append(line)
    return out


# ── View log screen ─────────────────────────────────────────────────----------

def _view_log_screen(display, touch, keyboard, W, H):
    content = _read_log()
    lines = _wrap_lines(content) if content else ["(empty)"]
    scroll = 0
    max_visible = 14

    while True:
        sc = displayio.Group()
        ui.make_title_bar(sc, "BATTERY TIMER:LOG", "{}L".format(len(lines)))
        ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

        for i in range(max_visible):
            idx = scroll + i
            if idx >= len(lines):
                break
            l = label.Label(terminalio.FONT, text=lines[idx],
                            color=ui.C_GREEN, scale=1)
            l.anchor_point = (0.0, 0.0)
            l.anchored_position = (2, ui.CONTENT_Y + 2 + i * 18)
            sc.append(l)

        ui.make_footer(sc, "^ UP  v DOWN  ^ SWIPE UP=BACK")
        display.root_group = sc

        fd = False
        sx = sy = lx = ly = 0
        action = None

        while action is None:
            if keyboard:
                kbd = keyboard.poll()
                if kbd['escape']:
                    action = "back"
                elif kbd['up'] and scroll > 0:
                    scroll -= 1
                    break
                elif kbd['down'] and scroll + max_visible < len(lines):
                    scroll += 1
                    break

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
                                     swipe_edge=ui.SWIPE_EDGE,
                                     swipe_min_dist=ui.SWIPE_MIN)
                if g:
                    if g[0] == "SWIPE UP":
                        action = "back"
                    elif g[0] == "SWIPE DOWN" and scroll + max_visible < len(lines):
                        scroll += 1
                        break
                    elif g[0] == "SWIPE UP_GESTURE" and scroll > 0:
                        scroll -= 1
                        break

        display.root_group = displayio.Group()
        del sc
        gc.collect()

        if action == "back":
            break


# ── App entry point ─────────────────────────────────────────────────----------

def run(display, touch, keyboard, W, H):
    # ── Detect time source ─────────────────────────────────────────-----
    rtc_name = _try_external_rtc()
    tz = _get_tz()
    if rtc_name:
        source = "RTC:" + rtc_name
    else:
        ntp_label = _try_ntp(tz)
        if ntp_label:
            source = "NTP " + ntp_label
        else:
            _set_fallback()
            source = "FALLBACK"
    gc.collect()

    # ── Build scene ─────────────────────────────────---------------------
    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:BATTERY TIMER", "v1.0")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    src_lbl = label.Label(terminalio.FONT, text="SRC: " + source,
                          color=ui.C_GREEN_DIM, scale=1)
    src_lbl.anchor_point = (0.5, 0.5)
    src_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 10)
    sc.append(src_lbl)
    ui.solid_rect(sc, 4, ui.CONTENT_Y + 20, W - 8, 1, ui.C_GREEN_DIM)

    time_lbl = label.Label(terminalio.FONT, text="TIME: --:--",
                           color=ui.C_GREEN_HI, scale=2)
    time_lbl.anchor_point = (0.5, 0.5)
    time_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 44)
    sc.append(time_lbl)

    run_lbl = label.Label(terminalio.FONT, text="RUN: STOPPED",
                          color=ui.C_AMBER, scale=2)
    run_lbl.anchor_point = (0.5, 0.5)
    run_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 74)
    sc.append(run_lbl)

    tally_lbl = label.Label(terminalio.FONT, text="",
                            color=ui.C_GREEN_MID, scale=1)
    tally_lbl.anchor_point = (0.5, 0.0)
    tally_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 100)
    sc.append(tally_lbl)

    sz_lbl = label.Label(terminalio.FONT, text="LOG: 0 B",
                         color=ui.C_GREEN_DIM, scale=1)
    sz_lbl.anchor_point = (0.5, 0.0)
    sz_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 126)
    sc.append(sz_lbl)

    # Start/Stop button
    btn_x = 30
    btn_y = ui.CONTENT_Y + 155
    btn_w = W - 60
    btn_h = 34
    btn_pal, btn_lbl = ui.make_button(sc, btn_x, btn_y, btn_w, btn_h,
                                      "START", bg_color=ui.C_BG_PANEL,
                                      text_color=ui.C_GREEN_HI)
    ui.make_border(sc, btn_x, btn_y, btn_w, btn_h, ui.C_GREEN_MID)

    # View Log button
    view_x = 30
    view_y = ui.CONTENT_Y + 196
    view_w = W - 60
    view_h = 34
    view_pal, view_lbl = ui.make_button(sc, view_x, view_y, view_w, view_h,
                                        "VIEW LOG", bg_color=ui.C_BG_PANEL,
                                        text_color=ui.C_GREEN_MID)
    ui.make_border(sc, view_x, view_y, view_w, view_h, ui.C_GREEN_DIM)

    ui.make_footer(sc, "ESC or SWIPE UP to quit")
    display.root_group = sc

    def _update_size():
        sz = _file_size(_LOG_FILE)
        sz_lbl.text = "LOG: {} B".format(sz) if sz >= 0 else "LOG: missing"

    _update_size()

    # ── Event loop ─────────────────────────────────---------------------
    running = False
    start_mono = 0
    last_log_min = -1
    last_sec = -1
    log_fh = None

    fd = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        t = time.localtime()
        if t.tm_sec != last_sec:
            last_sec = t.tm_sec
            time_lbl.text = "TIME: {:02d}:{:02d}".format(t.tm_hour, t.tm_min)

            if running:
                elapsed = int(time.monotonic() - start_mono)
                run_lbl.text = "RUN: " + _format_runtime(elapsed)
                mins = elapsed // 60
                if mins > last_log_min:
                    last_log_min = mins
                    tally_lbl.text = _make_tally(mins)
                    line = "{:02d}:{:02d} ({} minutes)\n".format(t.tm_hour, t.tm_min, mins)
                    if log_fh:
                        try:
                            log_fh.write(line)
                            log_fh.flush()
                            os.sync()
                        except OSError:
                            pass
                    _update_size()
            else:
                run_lbl.text = "RUN: STOPPED"

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
                                 swipe_edge=ui.SWIPE_EDGE,
                                 swipe_min_dist=ui.SWIPE_MIN)
            if g and g[0] == "SWIPE UP":
                break
            elif g and g[0] == "TAP":
                if btn_x <= sx <= btn_x + btn_w and btn_y <= sy <= btn_y + btn_h:
                    if not running:
                        running = True
                        start_mono = time.monotonic()
                        last_log_min = -1
                        tally_lbl.text = ""
                        try:
                            log_fh = open(_LOG_FILE, "w")
                            log_fh.flush()
                            os.sync()
                        except OSError:
                            running = False
                        _update_size()
                        if running:
                            btn_lbl.text = "STOP"
                            run_lbl.color = ui.C_GREEN_HI
                    else:
                        running = False
                        if log_fh:
                            try:
                                log_fh.close()
                            except OSError:
                                pass
                            log_fh = None
                        btn_lbl.text = "START"
                        run_lbl.color = ui.C_AMBER
                        _update_size()
                elif view_x <= sx <= view_x + view_w and view_y <= sy <= view_y + view_h:
                    _update_size()
                    _view_log_screen(display, touch, keyboard, W, H)

    # Clean up
    if log_fh:
        try:
            log_fh.close()
        except OSError:
            pass

    display.root_group = displayio.Group()
    del sc
    gc.collect()