# apps/network/app.py
# CyberDeck app: Network | portrait 240x320
#
# - Toggle WiFi on / off
# - Show current IP address and connected SSID
# - Scan visible networks and list them with signal strength + auth type
# - Swipe LEFT / RIGHT to page through results if > 5 networks found

import displayio
import terminalio
import time
import gc
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

# ── Layout constants ──────────────────────────────────────────────────────────
_TOGGLE_Y = ui.CONTENT_Y        # 21  — WiFi on/off button
_TOGGLE_H = 44
_IP_Y     = _TOGGLE_Y + _TOGGLE_H + 2   # 67  — IP / SSID info strip
_IP_H     = 22
_SEP1_Y   = _IP_Y + _IP_H + 2           # 91
_SCAN_Y   = _SEP1_Y + 2                 # 93  — scan button
_SCAN_H   = 36
_SEP2_Y   = _SCAN_Y + _SCAN_H + 2      # 131
_LIST_Y   = _SEP2_Y + 2                 # 133 — network rows
_ROW_H    = 30
_MAX_ROWS = 5                            # 5 x 30 = 150 px  → list ends y=283
_PAGE_Y   = _LIST_Y + _MAX_ROWS * _ROW_H  # 283


# ── WiFi helpers ──────────────────────────────────────────────────────────────

def _wifi_on():
    try:
        import wifi
        return bool(wifi.radio.enabled)
    except Exception:
        return False


def _set_wifi(state):
    try:
        import wifi
        wifi.radio.enabled = state
    except Exception:
        pass


def _get_ip():
    try:
        import wifi
        ip = wifi.radio.ipv4_address
        return str(ip) if ip else None
    except Exception:
        return None


def _get_connected_ssid():
    try:
        import wifi
        ap = wifi.radio.ap_info
        return ap.ssid if ap else None
    except Exception:
        return None


def _scan_networks():
    """
    Scan and return a list of dicts sorted by RSSI (strongest first).
    Networks sharing the same SSID are merged: best RSSI is kept and the
    count is stored so the UI can show e.g. "Warburton HQ [3]".
    """
    try:
        import wifi
        raw = list(wifi.radio.start_scanning_networks())
        wifi.radio.stop_scanning_networks()

        # Merge by SSID key (empty string for hidden networks)
        merged = {}
        for n in raw:
            key = n.ssid or ""
            if key in merged:
                merged[key]["count"] += 1
                if n.rssi > merged[key]["rssi"]:
                    merged[key]["rssi"]     = n.rssi
                    merged[key]["authmode"] = n.authmode
            else:
                merged[key] = {
                    "ssid":     n.ssid,
                    "rssi":     n.rssi,
                    "authmode": n.authmode,
                    "count":    1,
                }

        return sorted(merged.values(), key=lambda x: -x["rssi"])
    except Exception as e:
        print("network: scan error:", e)
        return []


def _auth_str(authmode):
    s = str(authmode)
    if "OPEN" in s:  return "OPEN"
    if "WPA3" in s:  return "WPA3"
    if "WPA2" in s:  return "WPA2"
    if "WPA"  in s:  return "WPA"
    if "WEP"  in s:  return "WEP"
    return "???"


def _sig_str(rssi):
    """4-char ASCII signal bar  e.g. '###.'"""
    if   rssi >= -55: bars = 4
    elif rssi >= -65: bars = 3
    elif rssi >= -75: bars = 2
    else:             bars = 1
    return "#" * bars + "." * (4 - bars)


# ── Entry point ───────────────────────────────────────────────────────────────

def run(display, touch, keyboard, W, H):
    networks = []
    page     = 0

    sc = displayio.Group()
    ui.make_title_bar(sc, "SYS:NETWORK", "v1.0")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    # ── WiFi toggle button ─────────────────────────────────────────────────
    toggle_pal = ui.solid_rect(sc, 4, _TOGGLE_Y, W - 8, _TOGGLE_H, ui.C_BG_PANEL)
    ui.make_border(sc, 4, _TOGGLE_Y, W - 8, _TOGGLE_H, ui.C_GREEN_MID)
    toggle_lbl = label.Label(terminalio.FONT, text="WIFI: ON",
                             color=ui.C_GREEN_HI, scale=2)
    toggle_lbl.anchor_point    = (0.5, 0.5)
    toggle_lbl.anchored_position = (W // 2, _TOGGLE_Y + _TOGGLE_H // 2)
    sc.append(toggle_lbl)

    # ── IP / SSID info strip ───────────────────────────────────────────────
    ui.solid_rect(sc, 4, _IP_Y, W - 8, _IP_H, ui.C_BG_PANEL)

    ip_lbl = label.Label(terminalio.FONT, text="IP: ---",
                         color=ui.C_GREEN_MID, scale=1)
    ip_lbl.anchor_point    = (0.0, 0.5)
    ip_lbl.anchored_position = (10, _IP_Y + _IP_H // 2)
    sc.append(ip_lbl)

    con_lbl = label.Label(terminalio.FONT, text="",
                          color=ui.C_GREEN_DIM, scale=1)
    con_lbl.anchor_point    = (1.0, 0.5)
    con_lbl.anchored_position = (W - 10, _IP_Y + _IP_H // 2)
    sc.append(con_lbl)

    # ── Separator ──────────────────────────────────────────────────────────
    ui.solid_rect(sc, 0, _SEP1_Y, W, 1, ui.C_GREEN_DIM)

    # ── Scan button ────────────────────────────────────────────────────────
    scan_pal = ui.solid_rect(sc, 4, _SCAN_Y, W - 8, _SCAN_H, ui.C_BG_PANEL)
    ui.make_border(sc, 4, _SCAN_Y, W - 8, _SCAN_H, ui.C_GREEN_MID)
    scan_lbl = label.Label(terminalio.FONT, text="SCAN NETWORKS",
                           color=ui.C_GREEN_HI, scale=2)
    scan_lbl.anchor_point    = (0.5, 0.5)
    scan_lbl.anchored_position = (W // 2, _SCAN_Y + _SCAN_H // 2)
    sc.append(scan_lbl)

    # ── Separator ──────────────────────────────────────────────────────────
    ui.solid_rect(sc, 0, _SEP2_Y, W, 1, ui.C_GREEN_DIM)

    # ── Network list rows (pre-allocated) ──────────────────────────────────
    row_objs = []
    for i in range(_MAX_ROWS):
        ry = _LIST_Y + i * _ROW_H
        if i > 0:
            ui.solid_rect(sc, 8, ry, W - 16, 1, ui.C_GREEN_DIM)
        # SSID (left)
        sl = label.Label(terminalio.FONT, text=" ",
                         color=ui.C_GREEN_HI, scale=1)
        sl.anchor_point    = (0.0, 0.0)
        sl.anchored_position = (8, ry + 4)
        sc.append(sl)
        # Signal + auth (right)
        rl = label.Label(terminalio.FONT, text=" ",
                         color=ui.C_GREEN_MID, scale=1)
        rl.anchor_point    = (1.0, 0.0)
        rl.anchored_position = (W - 8, ry + 4)
        sc.append(rl)
        # dBm (small, below SSID)
        dl = label.Label(terminalio.FONT, text=" ",
                         color=ui.C_GREEN_DIM, scale=1)
        dl.anchor_point    = (0.0, 0.0)
        dl.anchored_position = (8, ry + 17)
        sc.append(dl)
        row_objs.append((sl, rl, dl))

    # ── Empty-list message ─────────────────────────────────────────────────
    empty_lbl = label.Label(terminalio.FONT, text="TAP SCAN TO SEARCH",
                            color=ui.C_GREEN_DIM, scale=1)
    empty_lbl.anchor_point    = (0.5, 0.5)
    empty_lbl.anchored_position = (W // 2, _LIST_Y + 75)
    sc.append(empty_lbl)

    # ── Page indicator ─────────────────────────────────────────────────────
    page_lbl = label.Label(terminalio.FONT, text="",
                           color=ui.C_GREEN_DIM, scale=1)
    page_lbl.anchor_point    = (0.5, 0.5)
    page_lbl.anchored_position = (W // 2, _PAGE_Y + 8)
    sc.append(page_lbl)

    ui.make_footer(sc, "ESC or SWIPE UP to quit")
    display.root_group = sc

    # ── Refresh helpers ────────────────────────────────────────────────────

    def _refresh_status():
        on = _wifi_on()
        if on:
            toggle_pal[0]    = ui.C_BG_PANEL
            toggle_lbl.text  = "WIFI: ON"
            toggle_lbl.color = ui.C_GREEN_HI
            scan_pal[0]      = ui.C_BG_PANEL
            scan_lbl.color   = ui.C_GREEN_HI
        else:
            toggle_pal[0]    = 0x1A0000
            toggle_lbl.text  = "WIFI: OFF"
            toggle_lbl.color = ui.C_RED
            scan_pal[0]      = 0x0A0A0A
            scan_lbl.color   = ui.C_GREEN_DIM

        ip = _get_ip() if on else None
        if ip:
            ip_lbl.text  = "IP: " + ip
            ip_lbl.color = ui.C_GREEN_HI
        else:
            ip_lbl.text  = "IP: NOT CONNECTED"
            ip_lbl.color = ui.C_GREEN_DIM

        ssid = _get_connected_ssid() if on else None
        con_lbl.text = (ssid[:22] if ssid else "")

    def _refresh_list():
        nonlocal page
        if not networks:
            page = 0
        n_pages = max(1, (len(networks) + _MAX_ROWS - 1) // _MAX_ROWS)
        if page >= n_pages:
            page = n_pages - 1

        vis = networks[page * _MAX_ROWS: page * _MAX_ROWS + _MAX_ROWS]
        empty_lbl.text = "" if networks else "TAP SCAN TO SEARCH"

        for i, (sl, rl, dl) in enumerate(row_objs):
            if i < len(vis):
                n    = vis[i]
                base = n["ssid"] if n["ssid"] else "(hidden)"
                if n["count"] > 1:
                    tag  = " [{}]".format(n["count"])
                    ssid = base[:22 - len(tag)] + tag
                else:
                    ssid = base[:22]
                sl.text = ssid
                rl.text  = _sig_str(n["rssi"]) + " " + _auth_str(n["authmode"])
                dl.text  = "{} dBm".format(n["rssi"])
                sl.color = ui.C_GREEN_HI
                rl.color = ui.C_GREEN_MID
                dl.color = ui.C_GREEN_DIM
            else:
                sl.text = " "
                rl.text = " "
                dl.text = " "

        if n_pages > 1:
            page_lbl.text = "< PG {}/{} >".format(page + 1, n_pages)
        elif networks:
            page_lbl.text = "{} NETWORKS FOUND".format(len(networks))
        else:
            page_lbl.text = ""

    _refresh_status()
    _refresh_list()

    # ── Event loop ────────────────────────────────────────────────────────
    fd = False
    sx = sy = lx = ly = 0

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break

        x, y, tch = touch.read()
        time.sleep(0.04)

        if tch:
            lx, ly = x, y
            if not fd:
                fd = True
                sx, sy = x, y
        elif fd:
            fd = False
            g = classify_gesture(sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
            if not g:
                continue
            gk = g[0]

            if gk == "SWIPE UP":
                break

            elif gk == "SWIPE LEFT":
                n_pages = max(1, (len(networks) + _MAX_ROWS - 1) // _MAX_ROWS)
                if page < n_pages - 1:
                    page += 1
                    _refresh_list()

            elif gk == "SWIPE RIGHT":
                if page > 0:
                    page -= 1
                    _refresh_list()

            elif gk == "TAP":
                # WiFi toggle
                if _TOGGLE_Y <= sy <= _TOGGLE_Y + _TOGGLE_H:
                    _set_wifi(not _wifi_on())
                    if not _wifi_on():
                        networks = []
                        _refresh_list()
                    _refresh_status()

                # Scan button (WiFi must be on)
                elif _SCAN_Y <= sy <= _SCAN_Y + _SCAN_H:
                    if _wifi_on():
                        scan_lbl.text  = "SCANNING..."
                        scan_lbl.color = ui.C_AMBER
                        time.sleep(0.05)   # let display refresh before blocking
                        networks = _scan_networks()
                        page     = 0
                        scan_lbl.text  = "SCAN NETWORKS"
                        scan_lbl.color = ui.C_GREEN_HI
                        _refresh_list()
                        _refresh_status()  # IP may have changed

    display.root_group = displayio.Group()
    del sc
    gc.collect()
