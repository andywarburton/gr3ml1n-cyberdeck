# uart_keyboard.py - UART keyboard input reader
# Reads USB HID keycodes from KMK firmware over UART
# Protocol: Press:KeyboardKey(code=XX)\r\n, Release:KeyboardKey(code=XX)\r\n

import board
import busio

_UART_BAUD = 115200

# USB HID keycode to character mapping (codes 4-31 = a-z, 30-39 = 0-9)
_HID_MAP = {
    4: "a", 5: "b", 6: "c", 7: "d", 8: "e", 9: "f", 10: "g", 11: "h",
    12: "i", 13: "j", 14: "k", 15: "l", 16: "m", 17: "n", 18: "o", 19: "p",
    20: "q", 21: "r", 22: "s", 23: "t", 24: "u", 25: "v", 26: "w", 27: "x",
    28: "y", 29: "z",
    30: "1", 31: "2", 32: "3", 33: "4", 34: "5", 35: "6", 36: "7", 37: "8",
    38: "9", 39: "0",
    40: "_ENTER",  # Enter
    41: "_ESC",    # Escape
    42: "_BKSP",   # Backspace
    44: " ",       # Space
    45: "-", 47: "=", 46: "`",
    54: ",", 55: ".", 56: "/",
    47: "[", 48: "]", 49: "\\",
    51: ";", 52: "'",
    82: "_UP",     # Up arrow
    81: "_DOWN",    # Down arrow
}

_instance = None

print("uart_keyboard module loaded")


def get_keyboard():
    global _instance
    if _instance is None:
        _instance = UartKeyboard()
    return _instance


def _parse_code(s):
    """Extract keycode number from 'KeyboardKey(code=13)' string."""
    try:
        start = s.find("code=")
        if start >= 0:
            num_str = s[start + 5:]
            num_str = num_str.split(")")[0].strip()
            return int(num_str)
    except (ValueError, IndexError):
        pass
    return None


class UartKeyboard:
    def __init__(self, rx=board.RX, tx=board.TX, baudrate=_UART_BAUD):
        self._uart = None
        try:
            self._uart = busio.UART(tx=tx, rx=rx, baudrate=baudrate, timeout=0)
        except Exception as e:
            print("UART init error: " + str(e))
        self._buffer = ""

    def poll(self):
        result = {
            'char': None,
            'delete': False,
            'enter': False,
            'up': False,
            'down': False,
            'escape': False,
        }
        
        if self._uart is None:
            return result
        
        try:
            data = self._uart.read(256)
            if data:
                self._buffer += data.decode('utf-8', 'ignore')
        except Exception:
            pass

        while '\r\n' in self._buffer:
            line, self._buffer = self._buffer.split('\r\n', 1)
            
            if line.startswith("Press:"):
                code = _parse_code(line)
                if code is not None:
                    if code in _HID_MAP:
                        val = _HID_MAP[code]
                        if val.startswith("_"):
                            if val == "_ENTER":
                                result['enter'] = True
                            elif val == "_ESC":
                                result['escape'] = True
                            elif val == "_BKSP":
                                result['delete'] = True
                            elif val == "_UP":
                                result['up'] = True
                            elif val == "_DOWN":
                                result['down'] = True
                        else:
                            result['char'] = val

        return result

    def deinit(self):
        if self._uart:
            self._uart.deinit()
