# uart_keyboard.py - UART keyboard input reader
# Reads USB HID keycodes from KMK firmware over UART
# Protocol: Press:KeyboardKey(code=XX)\r\n, Release:KeyboardKey(code=XX)\r\n
# Now supports shift tracking for uppercase letters and shifted symbols.

import board
import busio

_UART_BAUD = 115200

# ── HID keycode → unshifted character ─────────────────────────────────────────
_HID_MAP = {
    # Letters a-z (codes 4-29)
    4: "a", 5: "b", 6: "c", 7: "d", 8: "e", 9: "f", 10: "g", 11: "h",
    12: "i", 13: "j", 14: "k", 15: "l", 16: "m", 17: "n", 18: "o", 19: "p",
    20: "q", 21: "r", 22: "s", 23: "t", 24: "u", 25: "v", 26: "w", 27: "x",
    28: "y", 29: "z",
    # Numbers 0-9 (codes 30-39)
    30: "1", 31: "2", 32: "3", 33: "4", 34: "5", 35: "6", 36: "7", 37: "8",
    38: "9", 39: "0",
    # Special actions
    40: "_ENTER",
    41: "_ESC",
    42: "_BKSP",
    44: " ",
    # Symbols
    45: "-",
    46: "=",
    47: "[",
    48: "]",
    49: "\\",
    50: "#",
    51: ";",
    52: "'",
    53: "`",
    54: ",",
    55: ".",
    56: "/",
    # Arrows
    79: "_RIGHT",
    80: "_LEFT",
    81: "_DOWN",
    82: "_UP",
}

# ── Shifted symbols (key → shifted version) ───────────────────────────────────
_SHIFT_MAP = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|",
    "#": "~", ";": ":", "'": '"', "`": "~", ",": "<",
    ".": ">", "/": "?",
}

# ── Empty result template ─────────────────────────────────────────────────────
_EMPTY = {
    'char': None,
    'delete': False,
    'enter': False,
    'up': False,
    'down': False,
    'left': False,
    'right': False,
    'escape': False,
    'keycode': None,
}

_instance = None

print("uart_keyboard module loaded")


def get_keyboard():
    global _instance
    if _instance is None:
        _instance = UartKeyboard()
    return _instance


# ── Protocol parsers ──────────────────────────────────────────────────────────

def _parse_keyboard_code(line):
    """Extract keycode from 'KeyboardKey(code=13)' inside a line."""
    try:
        start = line.find("KeyboardKey(code=")
        if start >= 0:
            num_str = line[start + 17:]
            num_str = num_str.split(")")[0].strip()
            return int(num_str)
    except (ValueError, IndexError):
        pass
    return None


def _parse_modifier_code(line):
    """Extract modifier code from 'ModifierKey(code=2)' inside a line."""
    try:
        start = line.find("ModifierKey(code=")
        if start >= 0:
            num_str = line[start + 17:]
            num_str = num_str.split(")")[0].strip()
            return int(num_str)
    except (ValueError, IndexError):
        pass
    return None


# ── Keyboard class ────────────────────────────────────────────────────────────

class UartKeyboard:
    def __init__(self, rx=board.RX, tx=board.TX, baudrate=_UART_BAUD):
        self._uart = None
        try:
            self._uart = busio.UART(tx=tx, rx=rx, baudrate=baudrate, timeout=0)
        except Exception as e:
            print("UART init error: " + str(e))
        self._buffer = ""
        self._shift = False
        self._pending = []

    def poll(self):
        """
        Return the next keyboard event as a dict.
        Events are queued so rapid typing doesn't lose characters.
        """
        if self._uart is not None:
            try:
                data = self._uart.read(256)
                if data:
                    self._buffer += data.decode('utf-8', 'ignore')
            except Exception:
                pass

            # Drain all complete lines from the buffer
            while '\r\n' in self._buffer:
                line, self._buffer = self._buffer.split('\r\n', 1)
                self._process_line(line)

        # Return next queued event, or empty dict
        if self._pending:
            return self._pending.pop(0)
        return dict(_EMPTY)

    def _process_line(self, line):
        """Parse a single protocol line and queue an event if needed."""
        if line.startswith("Press:"):
            is_press = True
        elif line.startswith("Release:"):
            is_press = False
        else:
            return

        has_mod = "ModifierKey" in line
        has_key = "KeyboardKey" in line

        # ── Track shift state ─────────────────────────────────────────────
        # Modifier code 2 = Left Shift. Update state on press / release.
        # If a release line also contains a KeyboardKey, it's a combo event
        # (key released while modifier still held) — don't clear shift yet.
        if has_mod:
            mod_code = _parse_modifier_code(line)
            if mod_code == 2:
                if is_press:
                    self._shift = True
                elif not has_key:
                    self._shift = False

        # ── Process keyboard key press ────────────────────────────────────
        if is_press and has_key:
            code = _parse_keyboard_code(line)
            if code is not None:
                ev = self._code_to_event(code)
                if ev is not None:
                    self._pending.append(ev)

    def _code_to_event(self, code):
        """Convert a HID keycode to a result dict."""
        if code not in _HID_MAP:
            return None

        val = _HID_MAP[code]
        ev = dict(_EMPTY)
        ev['keycode'] = code

        if val.startswith("_"):
            # Special / action key
            if val == "_ENTER":
                ev['enter'] = True
            elif val == "_ESC":
                ev['escape'] = True
            elif val == "_BKSP":
                ev['delete'] = True
            elif val == "_UP":
                ev['up'] = True
            elif val == "_DOWN":
                ev['down'] = True
            elif val == "_LEFT":
                ev['left'] = True
            elif val == "_RIGHT":
                ev['right'] = True
            else:
                return None
        else:
            # Character key — apply shift if active
            ch = val
            if self._shift:
                if len(ch) == 1 and 'a' <= ch <= 'z':
                    ch = ch.upper()
                elif ch in _SHIFT_MAP:
                    ch = _SHIFT_MAP[ch]
            ev['char'] = ch

        return ev

    def deinit(self):
        if self._uart:
            self._uart.deinit()
