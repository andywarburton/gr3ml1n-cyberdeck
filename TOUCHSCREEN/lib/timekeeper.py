# lib/timekeeper.py
# CyberDeck shared time source library
# Hierarchy: external I2C RTC → NTP via WiFi → fallback 13:13:00
#
# Usage:
#   import timekeeper
#   timekeeper.sync()          # run once at boot
#   t = time.localtime()       # use CircuitPython's normal time API
#
#   # Or for UI formatting:
#   timekeeper.now_str()       # "HH:MM"
#   timekeeper.now_str(True)   # "HH:MM:SS"

import time
import rtc as _rtc
import os

# ── Public state ─────────────────────────────────────────────────────────────
source_name = "UNKNOWN"   # "RTC:DS3231", "NTP:CET UTC+1", "FALLBACK", etc.


# ── Internal helpers ─────────────────────────────────────────────────────────

def _get_tz():
    """Read TZ_OFFSET (integer hours) from settings.toml, default 0."""
    try:
        return int(os.getenv("TZ_OFFSET") or "0")
    except Exception:
        return 0


def _unix_to_struct_time(unix_secs):
    """Integer-only Unix → struct_time conversion."""
    _MDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def _leap(y):
        return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)

    s    = int(unix_secs)
    sec  = s % 60;  s //= 60
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
    mon  = 1
    for m in range(12):
        mlen = _MDays[m] + (1 if m == 1 and _leap(year) else 0)
        if s < mlen:
            break
        s -= mlen
        mon += 1

    return time.struct_time((year, mon, s + 1, hour, min_, sec, wday, yday, -1))


def _eu_dst(year, month, mday, utc_hour):
    """Return True if European Summer Time (CEST) is active."""
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
    else:  # October
        if mday < ls:
            return True
        if mday > ls:
            return False
        return utc_hour < 1


def _try_external_rtc():
    """Scan I2C for RTC modules and sync the internal RTC. Returns name or None."""
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
                return "RTC:DS3231"
            except Exception:
                pass
            try:
                import adafruit_pcf8523
                ext = adafruit_pcf8523.PCF8523(i2c)
                _rtc.RTC().datetime = ext.datetime
                i2c.deinit()
                return "RTC:PCF8523"
            except Exception:
                pass

        if 0x51 in addrs:
            try:
                import adafruit_pcf8563
                ext = adafruit_pcf8563.PCF8563(i2c)
                _rtc.RTC().datetime = ext.datetime
                i2c.deinit()
                return "RTC:PCF8563"
            except Exception:
                pass

        i2c.deinit()
    except Exception as e:
        if "in use" not in str(e).lower():
            print("timekeeper: RTC probe:", e)
    return None


def _try_ntp(tz_base):
    """Fetch time via UDP from pool.ntp.org. Returns label string or None."""
    try:
        import wifi, socketpool, struct

        ssid = os.getenv("CIRCUITPY_WIFI_SSID")
        pwd  = os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""
        if not ssid:
            return None
        if not wifi.radio.ipv4_address:
            wifi.radio.connect(ssid, pwd)

        pool   = socketpool.SocketPool(wifi.radio)
        packet = bytearray(48)
        packet[0] = 0x1B

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
            raise Exception("short response")

        ntp_secs = struct.unpack_from("!I", resp, 40)[0]
        if ntp_secs < 3786825600:
            raise Exception("implausible timestamp")

        unix_utc = ntp_secs - 2208988800
        t_utc    = _unix_to_struct_time(unix_utc)
        dst      = _eu_dst(t_utc.tm_year, t_utc.tm_mon, t_utc.tm_mday, t_utc.tm_hour)
        offset   = tz_base + (1 if dst else 0)

        _rtc.RTC().datetime = _unix_to_struct_time(unix_utc + offset * 3600)

        name = "CEST" if dst else "CET"
        return "NTP:{} UTC+{}".format(name, offset)
    except Exception as e:
        print("timekeeper: NTP:", e)
        return None


def _set_fallback():
    """Set internal RTC to 13:13:00 so time.localtime() works."""
    try:
        _rtc.RTC().datetime = time.struct_time((2025, 1, 1, 13, 13, 0, 2, 1, -1))
    except Exception:
        pass


# ── Public API ───────────────────────────────────────────────────────────────

def sync(force_ntp=False):
    """
    Synchronise the internal RTC using the best available source.

    Priority:
        1. External I2C RTC (DS3231 / PCF8523 / PCF8563)
        2. NTP via WiFi (if credentials in settings.toml)
        3. Fallback 13:13:00

    Set *force_ntp=True* to skip the RTC probe (useful when you know
    the RTC is not present and want to avoid the brief I2C delay).
    """
    global source_name

    if not force_ntp:
        rtc_name = _try_external_rtc()
        if rtc_name:
            source_name = rtc_name
            print("timekeeper: source =", source_name)
            return source_name

    tz = _get_tz()
    ntp_label = _try_ntp(tz)
    if ntp_label:
        source_name = ntp_label
        print("timekeeper: source =", source_name)
        return source_name

    _set_fallback()
    source_name = "FALLBACK 13:13"
    print("timekeeper: source =", source_name)
    return source_name


def now_str(seconds=False):
    """Return current local time as a formatted string."""
    try:
        t = time.localtime()
        if seconds:
            return "{:02d}:{:02d}:{:02d}".format(t.tm_hour, t.tm_min, t.tm_sec)
        return "{:02d}:{:02d}".format(t.tm_hour, t.tm_min)
    except Exception:
        return "--:--" if not seconds else "--:--:--"
