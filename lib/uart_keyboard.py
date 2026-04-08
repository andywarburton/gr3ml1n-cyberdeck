# uart_keyboard.py - UART keyboard input reader
# Reads keycodes from KMK firmware over UART
# Protocol: P:KEYCODE\\r\\n (pressed), R:KEYCODE\\r\\n (released)

import board
import busio
import time

_UART_BAUD = 115200

# Keycode to character mapping
_KEYCODE_MAP = {
    "KC.A": "a", "KC.B": "b", "KC.C": "c", "KC.D": "d",
    "KC.E": "e", "KC.F": "f", "KC.G": "g", "KC.H": "h",
    "KC.I": "i", "KC.J": "j", "KC.K": "k", "KC.L": "l",
    "KC.M": "m", "KC.N": "n", "KC.O": "o", "KC.P": "p",
    "KC.Q": "q", "KC.R": "r", "KC.S": "s", "KC.T": "t",
    "KC.U": "u", "KC.V": "v", "KC.W": "w", "KC.X": "x",
    "KC.Y": "y", "KC.Z": "z",
    "KC.N0": "0", "KC.N1": "1", "KC.N2": "2", "KC.N3": "3",
    "KC.N4": "4", "KC.N5": "5", "KC.N6": "6", "KC.N7": "7",
    "KC.N8": "8", "KC.N9": "9",
    "KC.SPACE": " ",
    "KC.MINUS": "-", "KC.EQUAL": "=",
    "KC.LBRACKET": "[", "KC.RBRACKET": "]",
    "KC.BSLASH": "\\", "KC.SCOLON": ";", "KC.QUOTE": "'",
    "KC.GRAVE": "`", "KC.COMMA": ",", "KC.DOT": ".", "KC.SLASH": "/",
}

_DELETE_KEYS = {"KC.BKSP", "KC.DELETE", "KC.DEL"}
_ENTER_KEY = "KC.ENTER"


class UartKeyboard:
    def __init__(self, rx=board.RX, tx=board.TX, baudrate=_UART_BAUD):
        self._uart = busio.UART(rx, tx, baudrate=baudrate, timeout=0.01)
        self._buffer = ""
        self._enabled = False
        self._pressed_keys = set()

    def poll(self):
        """Poll for keypresses. Returns dict with:
        - 'char': character pressed (str) or None
        - 'delete': True if delete pressed
        - 'enter': True if enter pressed
        - 'enabled': True if uart keyboard is active
        """
        result = {
            'char': None,
            'delete': False,
            'enter': False,
            'enabled': self._enabled
        }
        
        try:
            data = self._uart.read(64)
            if data:
                self._buffer += data.decode('utf-8', errors='ignore')
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
                elif action == 'P' and keycode in _KEYCODE_MAP:
                    result['char'] = _KEYCODE_MAP[keycode]
                    self._pressed_keys.add(keycode)
                elif action == 'R':
                    self._pressed_keys.discard(keycode)

        return result

    def deinit(self):
        self._uart.deinit()
