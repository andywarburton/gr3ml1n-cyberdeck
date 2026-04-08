# waveshare_touch.py - Touch driver for Waveshare ESP32-S3 Touch LCD 2.8
#
# Physical (landscape) coordinate formulas for the touch IC at I2C address 0x1A:
#   raw_x = (buf[2] << 4) | (buf[3] >> 4)   -- physical 0..319 (12-bit)
#   raw_y = (14 - buf[1]) * 240 // 14        -- physical 0..239 (15 levels)
#   Touch active when buf[0] != 0x00
#
# Rotation support:
#   rotation=0   → landscape 320×240, no transform  (default)
#   rotation=90  → portrait  240×320, 90° clockwise
#                  portrait_x = raw_y          (0..239)
#                  portrait_y = 319 - raw_x    (0..319)
#   rotation=270 → portrait  240×320, 90° counter-clockwise
#                  portrait_x = 239 - raw_y
#                  portrait_y = raw_x
#
# Usage::
#
#     from waveshare_touch import WaveshareTouch, classify_gesture
#
#     touch = WaveshareTouch(board.TP_SCL, board.TP_SDA, board.TP_RST, rotation=90)
#     x, y, touching = touch.read()

import busio
import digitalio
import time

# Physical display dimensions (landscape, hardware fixed)
_PHYS_W = 320
_PHYS_H = 240


class WaveshareTouch:
    """Low-level touch reader for the Waveshare ESP32-S3 Touch LCD 2.8."""

    DEFAULT_ADDR = 0x1A

    def __init__(self, scl, sda, rst, addr=DEFAULT_ADDR, freq=400_000, rotation=0):
        self._addr     = addr
        self._rotation = rotation

        # Hardware reset
        _rst = digitalio.DigitalInOut(rst)
        _rst.direction = digitalio.Direction.OUTPUT
        _rst.value = False
        time.sleep(0.05)
        _rst.value = True
        time.sleep(0.1)

        self._i2c = busio.I2C(scl=scl, sda=sda, frequency=freq)

        # Enable periodic interrupt mode so touch data arrives continuously
        self._write_reg(0xFA, 0x01)

    def _write_reg(self, reg, val):
        while not self._i2c.try_lock():
            pass
        try:
            self._i2c.writeto(self._addr, bytes([reg, val]))
        except OSError as e:
            print("waveshare_touch write_reg:", e)
        finally:
            self._i2c.unlock()

    def scan(self):
        """Return list of I2C addresses found on the bus."""
        while not self._i2c.try_lock():
            pass
        found = self._i2c.scan()
        self._i2c.unlock()
        return found

    def read(self, _screen_h=None):
        """
        Read one touch frame.

        :param _screen_h: Deprecated — retained for backwards compatibility only.
                          Physical height is always 240; rotation is set at init time.
        :returns: (x, y, touching) in rotated screen-pixel coordinates.
                  Returns (0, 0, False) on I2C error or no touch.
        """
        buf = bytearray(16)
        while not self._i2c.try_lock():
            pass
        try:
            self._i2c.writeto_then_readfrom(self._addr, bytes([0x00]), buf)
        except OSError as e:
            print("waveshare_touch read:", e)
            return 0, 0, False
        finally:
            self._i2c.unlock()

        if buf[0] == 0x00:
            return 0, 0, False

        # Physical (landscape) coordinates
        raw_x = (buf[2] << 4) | (buf[3] >> 4)
        raw_y = (14 - buf[1]) * _PHYS_H // 14

        r = self._rotation
        if r == 90:
            # 90° clockwise: right side becomes top
            return raw_y, _PHYS_W - 1 - raw_x, True
        if r == 270:
            # 90° counter-clockwise: left side becomes top
            return _PHYS_H - 1 - raw_y, raw_x, True
        if r == 180:
            return _PHYS_W - 1 - raw_x, _PHYS_H - 1 - raw_y, True
        # rotation == 0: landscape, no transform
        return raw_x, raw_y, True


def classify_gesture(sx, sy, ex, ey,
                     screen_w, screen_h,
                     swipe_edge=35, swipe_min_dist=30,
                     buttons=None, btn_y=0, btn_h=0, btn_w=80, btn_y_margin=20):
    """
    Classify a completed touch (start → end) into an action.

    Works for any rotation — pass the rotated screen_w / screen_h.

    Swipe: finger started within *swipe_edge* px of an edge and travelled
           at least *swipe_min_dist* px toward the centre.

    Button tap: start Y falls within the button row (plus *btn_y_margin*
                tolerance) and start X falls within a button's width.

    Generic tap: short movement anywhere else.

    :param sx, sy:          Touch-start screen coordinates (rotated).
    :param ex, ey:          Touch-end (last known) screen coordinates.
    :param screen_w:        Display width in pixels (after rotation).
    :param screen_h:        Display height in pixels (after rotation).
    :param swipe_edge:      Edge-zone thickness in pixels.
    :param swipe_min_dist:  Minimum travel (px) to register a swipe.
    :param buttons:         List of button dicts with keys "x" and "label".
    :param btn_y:           Top Y pixel of the button row.
    :param btn_h:           Height of the button row in pixels.
    :param btn_w:           Width of each button in pixels.
    :param btn_y_margin:    Extra Y tolerance above/below the button row.
    :returns: (text, kind) or (text, kind, btn_index) for button taps.
    """
    dx = ex - sx
    dy = ey - sy
    dist = (dx * dx + dy * dy) ** 0.5

    # Edge swipe
    if dist >= swipe_min_dist:
        if sy < swipe_edge and dy > 0:
            return "SWIPE DOWN",  "swipe"
        if sy > screen_h - swipe_edge and dy < 0:
            return "SWIPE UP",    "swipe"
        if sx < swipe_edge and dx > 0:
            return "SWIPE RIGHT", "swipe"
        if sx > screen_w - swipe_edge and dx < 0:
            return "SWIPE LEFT",  "swipe"

    # Button tap (expanded Y zone for coarse Y resolution)
    if buttons and (btn_y - btn_y_margin) <= sy <= (btn_y + btn_h + btn_y_margin):
        for i, btn in enumerate(buttons):
            if btn["x"] <= sx <= btn["x"] + btn_w:
                return f'TAP: {btn["label"]}', "button", i

    # Generic tap
    return "TAP", "tap"
