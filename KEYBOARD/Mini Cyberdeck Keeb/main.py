import board
import busio
import digitalio
import neopixel_write
from kmk.kmk_keyboard import KMKKeyboard
from kmk.keys import KC, make_key, ModifiedKey
from kmk.scanners import DiodeOrientation
from kmk.modules.layers import Layers
from kmk.modules.holdtap import HoldTap, HoldTapKey
from kmk.modules.layers import Layers, LayerKey

keyboard = KMKKeyboard()
keyboard.modules.append(Layers())
keyboard.modules.append(HoldTap())

uart = busio.UART(board.GP0, board.GP1, baudrate=115200)
uart_enabled = True

pixel_pin = digitalio.DigitalInOut(board.GP16)
pixel_pin.direction = digitalio.Direction.OUTPUT

def set_pixel(r, g, b):
    neopixel_write.neopixel_write(pixel_pin, bytearray([r, g, b]))  # RGB order

set_pixel(0, 128, 0)  # Start green (UART mode)

keyboard.col_pins = (
    board.GP8, board.GP7, board.GP6, board.GP5, board.GP4,
    board.GP27, board.GP28, board.GP26, board.GP15, board.GP14
)
keyboard.row_pins = (board.GP9, board.GP10, board.GP11, board.GP12)
keyboard.diode_orientation = DiodeOrientation.COL2ROW

keyboard.coord_mapping = [
0,1,2,3,4,5,6,7,8,9,
10,11,12,13,14,15,16,17,18,19,
20,21,22,23,24,25,26,27,28,29,
30,31,32,33,34,35,36,37,38,39,
]

def toggle_mode(key, keyboard, KC, coord_int=None):
    global uart_enabled
    uart_enabled = not uart_enabled
    if uart_enabled:
        uart.write(b"UART_ENABLED\r\n")
        print("========== UART ENABLED ==========")
        set_pixel(0, 128, 0)   # green
    else:
        uart.write(b"UART_DISABLED\r\n")
        print("========== HID ENABLED ==========")
        set_pixel(128, 0, 128) # purple

TOGGLE_MODE = make_key(names=('TOGGLE_MODE',), on_press=toggle_mode)
HT_ESC = KC.HT(KC.ESC, TOGGLE_MODE, prefer_hold=True, tap_time=3000)

keyboard.keymap = [
    [
        HT_ESC,  KC.UP,     KC.DOWN,  KC.LEFT, KC.RIGHT,      KC.SPACE, KC.ENT,  KC.TG(1), KC.LSFT, KC.BSPC,
        KC.Q,    KC.W,      KC.E,     KC.R,    KC.T,          KC.Y,     KC.U,    KC.I,     KC.O,     KC.P,
        KC.A,    KC.S,      KC.D,     KC.F,    KC.G,          KC.H,     KC.J,    KC.K,     KC.L,     KC.SCLN,
        KC.Z,    KC.X,      KC.C,     KC.V,    KC.B,          KC.N,     KC.M,    KC.COMM,  KC.DOT,   KC.SLSH,
    ],
    [
        HT_ESC,  KC.UP,     KC.DOWN,  KC.LEFT, KC.RIGHT,      KC.SPACE, KC.ENT,  KC.TG(1), KC.LSFT, KC.BSPC,
        KC.N1,   KC.N2,     KC.N3,    KC.N4,   KC.N5,         KC.N6,    KC.N7,   KC.N8,    KC.N9,    KC.N0,
        KC.EXLM, KC.AT,     KC.HASH,  KC.DLR,  KC.PERC,       KC.CIRC,  KC.AMPR, KC.ASTR,  KC.LPRN,  KC.RPRN,
        KC.PLUS, KC.MINUS,  KC.EQUAL, KC.LBRC, KC.RBRC,       KC.LCBR,  KC.RCBR, KC.COMM,  KC.DOT,   KC.BSLS,
    ],
]

def _key_name(key):
    if isinstance(key, ModifiedKey):
        return _key_name(key.modifier) + '+' + _key_name(key.key)
    return str(key)


class UartModule:
    def during_bootup(self, keyboard):
        pass

    def before_matrix_scan(self, keyboard):
        return None

    def after_matrix_scan(self, keyboard):
        return None

    def process_key(self, keyboard, key, is_pressed, int_coord):
        if isinstance(key, HoldTapKey):
            return key  # Not resolved yet — let HoldTap handle it
        if isinstance(key, LayerKey):
            return key  # Let Layers module handle layer switching
        if key is TOGGLE_MODE:
            return key  # Always let toggle fire regardless of current mode

        key_name = _key_name(key)

        if uart_enabled:
            msg = f"{'Press' if is_pressed else 'Release'}:{key_name}\r\n"
            uart.write(msg.encode())
            print(f"UART: {msg.strip()}")
            return None
        return key

    def before_hid_send(self, keyboard):
        pass

    def after_hid_send(self, keyboard):
        pass

    def on_powersave_enable(self, keyboard):
        pass

    def on_powersave_disable(self, keyboard):
        pass

    def deinit(self, keyboard):
        pass

keyboard.modules.append(UartModule())

if __name__ == "__main__":
    keyboard.go()
