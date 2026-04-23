# lib/battery_monitor.py
# CyberDeck battery monitor for Waveshare ESP32-S3-Touch-LCD-2.8B
# Supports BAT_ADC voltage divider + BAT_CONTROL / BAT_PWR digital pins.

import board
import analogio
import digitalio
import time

# ── Default calibration ──────────────────────────────────────────────────────
# The onboard voltage divider. Calibrate against a multimeter on the BAT pin.
DEFAULT_DIVIDER_RATIO = 1.87

# ── Pin discovery lists ──────────────────────────────────────────────────────
_ADC_PINS = ["BAT_ADC", "IO4", "GP4", "A4", "D4"]
_CTRL_PINS = ["BAT_CONTROL"]
_PWR_PINS = ["BAT_PWR"]

# ── Thresholds for 18650 Li-ion ──────────────────────────────────────────────
V_MAX = 4.2
V_NOMINAL = 3.6
V_LOW = 3.3
V_CRITICAL = 3.0
V_USB_THRESHOLD = 4.4   # above this = USB VBUS detected (battery switch off)


class BatteryMonitor:
    """
    Self-contained battery monitor for the Waveshare ESP32-S3-Touch-LCD-2.8B.
    Auto-discovers ADC and digital pins on first use.
    """

    def __init__(self, divider_ratio=DEFAULT_DIVIDER_RATIO):
        self._divider = float(divider_ratio)
        self._adc_pin = None
        self._ctrl_dio = None
        self._pwr_dio = None
        self._last_raw = 0
        self._last_pin_v = 0.0
        self._last_bat_v = 0.0
        self._last_read_time = 0
        self._initialized = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _init(self):
        if self._initialized:
            return
        self._adc_pin = self._find_adc_pin()
        self._ctrl_dio = self._open_digital_pin(_CTRL_PINS)
        self._pwr_dio = self._open_digital_pin(_PWR_PINS)
        self._initialized = True

    @staticmethod
    def _find_adc_pin():
        for name in _ADC_PINS:
            pin = getattr(board, name, None)
            if pin is not None:
                try:
                    adc = analogio.AnalogIn(pin)
                    raw = adc.value
                    adc.deinit()
                    return pin
                except Exception:
                    pass
        return None

    @staticmethod
    def _open_digital_pin(names):
        for name in names:
            pin = getattr(board, name, None)
            if pin is None:
                continue
            try:
                dio = digitalio.DigitalInOut(pin)
                dio.direction = digitalio.Direction.INPUT
                return dio
            except Exception:
                pass
        return None

    def _read_adc(self):
        if self._adc_pin is None:
            return 0, 0.0, 0.0
        try:
            adc = analogio.AnalogIn(self._adc_pin)
            raw = adc.value
            adc.deinit()
            pin_v = (raw / 65535.0) * 3.3
            bat_v = pin_v * self._divider
            return raw, pin_v, bat_v
        except Exception:
            return 0, 0.0, 0.0

    def _read_digital(self, dio):
        if dio is None:
            return None
        try:
            return bool(dio.value)
        except Exception:
            return None

    def _refresh(self):
        now = time.monotonic()
        # cache for 250 ms to avoid hammering the ADC
        if now - self._last_read_time < 0.25:
            return
        self._init()
        self._last_raw, self._last_pin_v, self._last_bat_v = self._read_adc()
        self._last_read_time = now

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def voltage(self):
        """Battery voltage in volts (float). Returns 0.0 if no ADC pin found."""
        self._refresh()
        return self._last_bat_v

    @property
    def percentage(self):
        """
        Estimated charge percentage (0-100).
        Returns -1 when running on USB power (no battery connected).
        """
        self._refresh()
        v = self._last_bat_v
        if v > V_USB_THRESHOLD:
            return -1
        if v <= V_CRITICAL:
            return 0
        pct = int(((v - V_CRITICAL) / (V_MAX - V_CRITICAL)) * 100)
        if pct > 100:
            pct = 100
        return pct

    @property
    def power_source(self):
        """
        Returns 'USB' when VBUS is detected (battery switch off or no cell),
        otherwise 'BATTERY'.
        """
        self._refresh()
        if self._last_bat_v > V_USB_THRESHOLD:
            return "USB"
        if self._last_bat_v > 0.1:
            return "BATTERY"
        return "UNKNOWN"

    @property
    def is_charging(self):
        """
        Best-effort charging detection.
        Returns True when USB is present and a battery is connected
        (inferred from voltage in the Li-ion range + digital pin states).
        """
        self._refresh()
        v = self._last_bat_v

        # No battery connected -> not charging
        if v > V_USB_THRESHOLD or v < 0.1:
            return False

        # If BAT_CONTROL or BAT_PWR are high, charger is likely active
        ctrl = self._read_digital(self._ctrl_dio)
        pwr = self._read_digital(self._pwr_dio)
        if ctrl is True or pwr is True:
            return True

        # Fallback: USB present implies charging when battery is in normal range
        # (This board's demo code loops battery checks while USB is plugged)
        return False

    @property
    def raw_adc(self):
        """Raw 16-bit ADC value (0-65535)."""
        self._refresh()
        return self._last_raw

    @property
    def pin_voltage(self):
        """Voltage at the ADC pin after the divider (0-3.3V)."""
        self._refresh()
        return self._last_pin_v

    @property
    def ctrl_state(self):
        """BAT_CONTROL pin state: True/High, False/Low, or None if unavailable."""
        self._init()
        return self._read_digital(self._ctrl_dio)

    @property
    def pwr_state(self):
        """BAT_PWR pin state: True/High, False/Low, or None if unavailable."""
        self._init()
        return self._read_digital(self._pwr_dio)

    def read(self):
        """
        Return a dictionary with all battery values at once.
        Useful for apps that want to update multiple UI fields.
        """
        self._refresh()
        return {
            "voltage": self.voltage,
            "percentage": self.percentage,
            "power_source": self.power_source,
            "is_charging": self.is_charging,
            "raw_adc": self.raw_adc,
            "pin_voltage": self.pin_voltage,
            "ctrl_state": self.ctrl_state,
            "pwr_state": self.pwr_state,
        }

    def deinit(self):
        """Release hardware resources. Call when app exits."""
        if self._ctrl_dio is not None:
            try:
                self._ctrl_dio.deinit()
            except Exception:
                pass
            self._ctrl_dio = None
        if self._pwr_dio is not None:
            try:
                self._pwr_dio.deinit()
            except Exception:
                pass
            self._pwr_dio = None
        self._initialized = False
