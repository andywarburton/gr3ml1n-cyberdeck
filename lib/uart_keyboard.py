# uart_keyboard.py - UART keyboard input reader
# Reads keycodes from KMK firmware over UART
# Protocol: P:KEYCODE\r\n (pressed), R:KEYCODE\r\n (released)

import board
import busio

_UART_BAUD = 115200

_KEYCODE_MAP = {
    "KC.A": "a", "KC.B": "b", "KC.C": "c", "KC.D": "d",
    "KC.E": "e", "KC.F": "f", "KC.G": "g", "KC.H": "h",
    "KC.I": "i", "KC.J": "j", "KC.K": "k", "KC.L": "l",
    "KC.M": "m", "KC.N": "n", "KC.O": "o", "KC.P": "p",
    "KC.Q": "q", "KC.R": "r", "KC.S": "s", "KC.T": "t",
    "KC.U": "u", "KC.V": "v", "KC.W": "w", "KC.X": "x",
    "KC.Y": "y", "KC.Z": "z",
    "KC.N1": "1", "KC.N2": "2", "KC.N3": "3",
    "KC.N4": "4", "KC.N5": "5", "KC.N6": "6",
    "KC.N7": "7", "KC.N8": "8", "KC.N9": "9", "KC.N0": "0",
    "KC.SPACE": " ",
    "KC.MINUS": "-", "KC.EQUAL": "=",
    "KC.LBRACKET": "[", "KC.RBRACKET": "]",
    "KC.BSLASH": "\\", "KC.SCOLON": ";", "KC.QUOTE": "'",
    "KC.GRAVE": "`", "KC.COMMA": ",", "KC.DOT": ".", "KC.SLASH": "/",
    "8": "1", "25": "2", "9": "3", "21": "4", "33": "5",
    "32": "6", "26": "7", "22": "8", "27": "9", "6": "0",
}

_DELETE_KEYS = {"KC.BKSP", "KC.DELETE", "KC.DEL", "7"}
_ENTER_KEY = "KC.ENTER"
_NAV_KEYS = {"KC.UP", "KC.DOWN", "KC.ESC", "KC.ESCAPE"}

_instance = None


def get_keyboard():
    global _instance
    if _instance is None:
        _instance = UartKeyboard()
    return _instance


class UartKeyboard:
    def __init__(self, rx=board.RX, tx=board.TX, baudrate=_UART_BAUD):
        self._uart = None
        try:
            self._uart = busio.UART(tx=tx, rx=rx, baudrate=baudrate, timeout=0)
        except Exception as e:
            print(f"UART init error: {e}")
        self._buffer = ""
        self._enabled = False

    def poll(self):
        result = {
            'char': None,
            'delete': False,
            'enter': False,
            'up': False,
            'down': False,
            'escape': False,
            'enabled': self._enabled
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
            
            if line == "UART_ENABLED":
                self._enabled = True
            elif line == "UART_DISABLED":
                self._enabled = False
            elif ':' in line:
                action, keycode = line.split(':', 1)
                
                if keycode in _DELETE_KEYS:
                    result['delete'] = True
                elif keycode == _ENTER_KEY:
                    result['enter'] = True
                elif keycode in _NAV_KEYS:
                    if action == 'P':
                        if keycode in ("KC.UP", "KC.ESC", "KC.ESCAPE"):
                            result['up' if keycode == "KC.UP" else 'escape'] = True
                        elif keycode == "KC.DOWN":
                            result['down'] = True
                elif action == 'P' and keycode in _KEYCODE_MAP:
                    result['char'] = _KEYCODE_MAP[keycode]

        return result

    def deinit(self):
        if self._uart:
            self._uart.deinit()
