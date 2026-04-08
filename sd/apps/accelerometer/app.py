# apps/accelerometer/app.py
# CyberDeck app: G-FORCE TRACKER | portrait 240x320
#
# Sci-fi radar display with:
# - Concentric radar rings with crosshairs
# - Animated rotating sweep wave
# - Blip that moves based on accelerometer X/Y tilt
# - Numeric G-force readouts

import displayio
import terminalio
import busio
import vectorio
import time
import gc
import math
import board
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

try:
    import qmi8658c
    _HAS_IMU = True
except Exception:
    _HAS_IMU = False

# ── Radar geometry ─────────────────────────────────────────────────────────────
RADAR_CX = 120
RADAR_CY = 165
RADAR_R  = 90
RING_SPACING = RADAR_R // 3

# ── Radar colors ────────────────────────────────────────────────────────────────
_C_RING     = ui.C_GREEN_DIM
_C_CROSS    = ui.C_GREEN_DIM
_C_SWEEP    = ui.C_GREEN_MID
_C_BLIP     = ui.C_GREEN_HI
_C_BLIP_GLOW = ui.C_GREEN_GLOW
_C_TRAIL    = ui.C_GREEN_DIM


class RadarDisplay:
    def __init__(self, scene):
        self.scene = scene
        self.sweep_angle = 0
        self.blip_x = RADAR_CX
        self.blip_y = RADAR_CY
        self.trail_points = []
        self._radar_group = displayio.Group()
        scene.append(self._radar_group)
        self._build_static()

    def _build_static(self):
        self._add_ring(RADAR_R)
        self._add_ring(RING_SPACING * 2)
        self._add_ring(RING_SPACING)
        self._add_crosshair()
        self._center_pal = ui.solid_rect(self._radar_group, RADAR_CX - 2, RADAR_CY - 2, 4, 4, _C_RING)
        
        self._sweep_group = displayio.Group()
        self._radar_group.append(self._sweep_group)
        self._blip_group = displayio.Group()
        self._radar_group.append(self._blip_group)
        self._trail_group = displayio.Group()
        self._radar_group.append(self._trail_group)

    def _add_ring(self, radius):
        pal = displayio.Palette(1)
        pal[0] = _C_RING
        self._radar_group.append(
            vectorio.Circle(pixel_shader=pal, radius=radius, x=RADAR_CX, y=RADAR_CY)
        )

    def _add_crosshair(self):
        ui.solid_rect(self._radar_group, RADAR_CX - RADAR_R, RADAR_CY - 1, RADAR_R * 2, 2, _C_CROSS)
        ui.solid_rect(self._radar_group, RADAR_CX - 1, RADAR_CY - RADAR_R, 2, RADAR_R * 2, _C_CROSS)

    def update(self, ax, ay, az):
        self.sweep_angle = (self.sweep_angle + 6) % 360
        
        # Try different axis combinations
        bx = max(-1, min(1, ax))
        by = max(-1, min(1, -ay))
        
        target_x = RADAR_CX + bx * (RADAR_R - 8)
        target_y = RADAR_CY - by * (RADAR_R - 8)
        
        self.blip_x = self.blip_x * 0.7 + target_x * 0.3
        self.blip_y = self.blip_y * 0.7 + target_y * 0.3
        
        self.trail_points.append((self.blip_x, self.blip_y))
        if len(self.trail_points) > 15:
            self.trail_points.pop(0)
        
        self._redraw()

    def _redraw(self):
        while len(self._sweep_group) > 0:
            self._sweep_group.pop()
        while len(self._blip_group) > 0:
            self._blip_group.pop()
        while len(self._trail_group) > 0:
            self._trail_group.pop()
        
        # Sweep fade trail
        for i in range(30, 0, -3):
            angle_rad = math.radians((self.sweep_angle - i * 2) % 360)
            fade = max(0.2, 1.0 - i / 30)
            cx = int(RADAR_CX + math.cos(angle_rad) * RADAR_R * fade)
            cy = int(RADAR_CY + math.sin(angle_rad) * RADAR_R * fade)
            if 0 <= cx <= 240 and 0 <= cy <= 320:
                size = max(1, int(3 * fade))
                color = _C_TRAIL if fade < 0.6 else _C_SWEEP
                ui.solid_rect(self._sweep_group, cx - size // 2, cy - size // 2, size, size, color)
        
        # Main sweep line
        angle_rad = math.radians(self.sweep_angle)
        for i in range(0, RADAR_R, 5):
            t = i / RADAR_R
            cx = int(RADAR_CX + math.cos(angle_rad) * i)
            cy = int(RADAR_CY + math.sin(angle_rad) * i)
            size = 2 if t > 0.1 else 1
            ui.solid_rect(self._sweep_group, cx - 1, cy - 1, size, size, _C_SWEEP)
        
        # Trail points
        for i, (tx, ty) in enumerate(self.trail_points):
            age = len(self.trail_points) - i
            alpha = max(0.3, 1.0 - (age / 20))
            size = max(2, int(4 * alpha))
            color = _C_TRAIL if alpha < 0.7 else _C_BLIP
            ui.solid_rect(self._trail_group, int(tx) - size // 2, int(ty) - size // 2, size, size, color)
        
        # Blip glow
        glow_size = 8
        ui.solid_rect(self._blip_group, 
                      int(self.blip_x) - glow_size // 2, 
                      int(self.blip_y) - glow_size // 2, 
                      glow_size, glow_size, _C_BLIP_GLOW)
        
        # Blip core
        core_size = 4
        ui.solid_rect(self._blip_group,
                      int(self.blip_x) - core_size // 2,
                      int(self.blip_y) - core_size // 2,
                      core_size, core_size, _C_BLIP)
        
        # Pulsing center
        pulse = (math.sin(time.monotonic() * 4) + 1) / 2
        self._center_pal[0] = ui.C_GREEN_HI if pulse > 0.5 else ui.C_GREEN_MID


def run(display, touch, keyboard, W, H):
    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:G-TRACKER", "RADAR-MODE")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    radar = RadarDisplay(scene)
    
    x_lbl = label.Label(terminalio.FONT, text="X: +0.00G", color=ui.C_GREEN_HI, scale=1)
    x_lbl.anchor_point = (0.0, 0.0)
    x_lbl.anchored_position = (8, ui.CONTENT_Y + 5)
    scene.append(x_lbl)

    y_lbl = label.Label(terminalio.FONT, text="Y: +0.00G", color=ui.C_GREEN_HI, scale=1)
    y_lbl.anchor_point = (0.0, 0.0)
    y_lbl.anchored_position = (W // 2 + 4, ui.CONTENT_Y + 5)
    scene.append(y_lbl)

    z_lbl = label.Label(terminalio.FONT, text="Z: +0.00G", color=ui.C_GREEN_DIM, scale=1)
    z_lbl.anchor_point = (0.0, 0.0)
    z_lbl.anchored_position = (8, ui.CONTENT_Y + 18)
    scene.append(z_lbl)

    ui.solid_rect(scene, 0, 260, W, 1, ui.C_GREEN_DIM)
    
    mag_lbl = label.Label(terminalio.FONT, text="MAG: 1.00G", color=ui.C_GREEN_HI, scale=2)
    mag_lbl.anchor_point = (0.5, 0.5)
    mag_lbl.anchored_position = (W // 2, 278)
    scene.append(mag_lbl)

    orient_lbl = label.Label(terminalio.FONT, text="[ CALIBRATED ]", color=ui.C_GREEN_DIM, scale=1)
    orient_lbl.anchor_point = (0.5, 0.5)
    orient_lbl.anchored_position = (W // 2, 295)
    scene.append(orient_lbl)

    imu = None
    if _HAS_IMU:
        try:
            i2c = busio.I2C(board.IO10, board.IO11)
            imu = qmi8658c.QMI8658C(i2c)
        except Exception as e:
            err_lbl = label.Label(terminalio.FONT, text=f"IMU ERR: {str(e)[:20]}", color=ui.C_RED, scale=1)
            err_lbl.anchor_point = (0.5, 0.5)
            err_lbl.anchored_position = (W // 2, 295)
            scene.append(err_lbl)
            imu = None
    else:
        err_lbl = label.Label(terminalio.FONT, text="[ SIMULATION ]", color=ui.C_AMBER, scale=1)
        err_lbl.anchor_point = (0.5, 0.5)
        err_lbl.anchored_position = (W // 2, 295)
        scene.append(err_lbl)

    ui.make_footer(scene, "ESC or SWIPE UP to quit")
    display.root_group = scene

    sim_time = 0
    finger_down = False
    sx = sy = lx = ly = 0
    
    while True:
        kbd = keyboard.poll()
        if kbd['escape']:
            break
            
        x, y, touching = touch.read()
        
        if touching:
            if not finger_down:
                finger_down = True
                sx, sy = x, y
            lx, ly = x, y
        elif finger_down:
            finger_down = False
            action = classify_gesture(sx, sy, lx, ly, W, H,
                                     swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
            if action and action[0] == "SWIPE UP":
                break
        
        if imu is not None:
            try:
                ax, ay, az = imu.acceleration
                ax_g = ax / 9.806
                ay_g = ay / 9.806
                az_g = az / 9.806
            except Exception:
                ax_g = ay_g = az_g = 0
        else:
            sim_time += 0.03
            ax_g = math.sin(sim_time * 1.3) * 0.5
            ay_g = math.cos(sim_time * 0.9) * 0.4
            az_g = 1.0 + math.sin(sim_time * 0.5) * 0.1

        radar.update(ax_g, ay_g, az_g)

        x_lbl.text = f"X:{ax_g:+.2f}"
        y_lbl.text = f"Y:{ay_g:+.2f}"
        z_lbl.text = f"Z:{az_g:+.2f}"

        magnitude = (ax_g**2 + ay_g**2 + az_g**2) ** 0.5
        mag_lbl.text = f"MAG:{magnitude:.2f}G"

        if abs(az_g) > 0.8 and abs(ax_g) < 0.3 and abs(ay_g) < 0.3:
            orient = "[ FLAT ]"
            mag_lbl.color = ui.C_GREEN_HI
        elif ax_g > 0.6:
            orient = "[ RIGHT ]"
            mag_lbl.color = ui.C_AMBER
        elif ax_g < -0.6:
            orient = "[ LEFT ]"
            mag_lbl.color = ui.C_AMBER
        elif ay_g > 0.6:
            orient = "[ FWD ]"
            mag_lbl.color = ui.C_AMBER
        elif ay_g < -0.6:
            orient = "[ BACK ]"
            mag_lbl.color = ui.C_AMBER
        elif az_g < -0.3:
            orient = "[ FLIP ]"
            mag_lbl.color = ui.C_RED
        else:
            orient = "[ ANGLED ]"
            mag_lbl.color = ui.C_GREEN_DIM
        orient_lbl.text = orient

        time.sleep(0.05)

    display.root_group = displayio.Group()
    gc.collect()
