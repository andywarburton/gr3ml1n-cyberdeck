# sd/apps/web_server/app.py
# CyberDeck app: Web Server | portrait 240x320
# AP mode hotspot + DNS captive portal + dual-port HTTP file server
# On-device START/STOP toggle

import displayio
import terminalio
import time
import gc
import os
import wifi
import socketpool
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui
from battery_monitor import BatteryMonitor
import timekeeper
from uart_keyboard import get_keyboard

# --- Config ---
HTTP_PORT_80 = 80
HTTP_PORT_666 = 666
DNS_PORT = 53
FALLBACK_IP = "192.168.4.1"
BUFFER_SIZE = 512
MAX_LOG = 5
CAPTIVE_PATHS = {
    "/hotspot-detect.html", "/generate_204", "/connecttest.txt",
    "/success.txt", "/check_network_status.txt", "/redirect",
    "/library/test/success.html", "/mobile/status.php",
}

_HTML_HEAD = b"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GR3ML1N</title><style>
body{background:#000;color:#0f0;font-family:monospace,Consolas,Courier New;margin:1em;font-size:14px;}
a{color:#0f0;text-decoration:none;}a:hover{color:#fff;}
table{width:100%;border-collapse:collapse;}
td{padding:6px 4px;border-bottom:1px solid #0f0300;}
.size{color:#555;margin-left:1em;font-size:12px;}
.breadcrumb{color:#0a0;margin-bottom:1em;padding:8px;background:#0f0300;}
.folder{font-weight:bold;}
input{background:#111;color:#0f0;border:1px solid #0f0;padding:4px;}
input[type=submit]{cursor:pointer;}input[type=submit]:hover{background:#0f0;color:#000;}
hr{border:0;border-top:1px solid #0f0300;margin:1em 0;}
</style></head><body><h2>GR3ML1N File Server</h2>"""

_HTML_FOOT = b"""</body></html>"""


def _quote(s):
    return s.replace(" ", "%20").replace("#", "%23").replace("&", "%26")


def _format_size(size):
    if size < 1024:
        return str(size) + " B"
    elif size < 1024 * 1024:
        return "{:.1f} KB".format(size / 1024)
    else:
        return "{:.1f} MB".format(size / (1024 * 1024))


def _ap_ip_bytes(ip_str):
    return bytes([int(x) for x in ip_str.split(".")])


def _dns_skip_name(pkt, offset):
    while offset < len(pkt):
        length = pkt[offset]
        if length & 0xC0 == 0xC0:
            return offset + 2
        if length == 0:
            return offset + 1
        offset += length + 1
    return offset


def _build_dns_response(data, ip_bytes):
    if len(data) < 12:
        return None
    q_end = _dns_skip_name(data, 12) + 4
    return (data[:2] + b'\x81\x80' +
            data[4:6] + b'\x00\x01\x00\x00\x00\x00' +
            data[12:q_end] +
            b'\xC0\x0C\x00\x01\x00\x01\x00\x00\x00\x3C\x00\x04' + ip_bytes)


def _parse_request(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        buf = bytearray(BUFFER_SIZE)
        n = sock.recv_into(buf)
        if n == 0:
            break
        data += bytes(buf[:n])
        if len(data) > 8192:
            break
    if not data or b"\r\n\r\n" not in data:
        return None
    header_end = data.find(b"\r\n\r\n")
    headers_raw = data[:header_end]
    body = data[header_end + 4:]
    lines = headers_raw.split(b"\r\n")
    if not lines:
        return None
    first = lines[0].decode("utf-8", "ignore")
    parts = first.split()
    if len(parts) < 2:
        return None
    method = parts[0]
    path = parts[1]
    headers = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers[k.strip().lower()] = v.strip()
    if method == "POST" and b"content-length" in headers:
        cl = int(headers[b"content-length"])
        while len(body) < cl:
            buf = bytearray(BUFFER_SIZE)
            n = sock.recv_into(buf)
            if n == 0:
                break
            body += bytes(buf[:n])
    return method, path, headers, body


def _parse_path(path):
    if "?" in path:
        pp, qp = path.split("?", 1)
    else:
        pp, qp = path, ""
    query = {}
    for pair in qp.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            query[k] = v
    return pp, query


def _validate_path(path):
    if not path.startswith("/sd/") and path != "/sd":
        return False
    if ".." in path:
        return False
    return True


def _content_type(path):
    ext = path.split(".")[-1].lower() if "." in path else ""
    types = {
        "txt": "text/plain", "py": "text/plain", "json": "application/json",
        "toml": "text/plain", "md": "text/plain", "csv": "text/plain",
        "log": "text/plain", "htm": "text/html", "html": "text/html",
        "bmp": "image/bmp", "png": "image/png",
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    }
    return types.get(ext, "application/octet-stream")


def _send_response(sock, status, content_type, body):
    hdr = "HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(
        status, content_type, len(body))
    sock.send(hdr.encode("utf-8") + body)


def _send_redirect(sock, location):
    hdr = "HTTP/1.1 302 Found\r\nLocation: {}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".format(location)
    sock.send(hdr.encode("utf-8"))


def _error_html(code, msg):
    return (_HTML_HEAD.decode("utf-8") +
            "<h1>Error {}</h1><p>{}</p>".format(code, msg) +
            _HTML_FOOT.decode("utf-8")).encode("utf-8")


def _captive_html(ip):
    return ("""<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="0;url=http://{}/browse?path=/sd">
</head><body>Redirecting...</body></html>""".format(ip)).encode("utf-8")


def _list_dir_html(path, ip):
    if not _validate_path(path):
        return _error_html(403, "Invalid path")
    try:
        entries = os.listdir(path)
    except OSError as e:
        return _error_html(404, "Not found")

    dirs = []
    files = []
    for e in entries:
        if e.startswith("."):
            continue
        full = path + "/" + e
        try:
            st = os.stat(full)
            if st[0] & 0x4000:
                dirs.append((e, st[6]))
            else:
                files.append((e, st[6]))
        except:
            files.append((e, 0))

    dirs.sort(key=lambda x: x[0].lower())
    files.sort(key=lambda x: x[0].lower())

    # Breadcrumb
    parts = path.split("/")
    crumb = '<div class="breadcrumb"><a href="/browse?path=/sd">/sd</a>'
    accum = "/sd"
    for p in parts[2:]:
        if p:
            accum += "/" + p
            crumb += ' / <a href="/browse?path={}">{}</a>'.format(_quote(accum), p)
    crumb += '</div>'

    # Table
    rows = []
    if path != "/sd":
        parent = "/".join(path.split("/")[:-1])
        if not parent:
            parent = "/sd"
        rows.append('<tr><td><a href="/browse?path={}">..</a></td><td></td></tr>'.format(_quote(parent)))

    for name, size in dirs:
        full = path + "/" + name
        rows.append('<tr><td class="folder"><a href="/browse?path={}">&#128193; {}</a></td><td></td></tr>'.format(_quote(full), name))

    for name, size in files:
        full = path + "/" + name
        size_str = _format_size(size)
        rows.append('<tr><td><a href="/file?path={}">&#128196; {}</a></td><td class="size">{}</td></tr>'.format(_quote(full), name, size_str))

    upload_form = ('<hr><form action="/upload?path={}" method="post" enctype="multipart/form-data">'
                   '<input type="file" name="file"><input type="submit" value="Upload"></form>').format(_quote(path))

    html = (_HTML_HEAD.decode("utf-8") + crumb + "<table>" + "".join(rows) + "</table>" +
            upload_form + _HTML_FOOT.decode("utf-8")).encode("utf-8")
    return html


def _serve_file(sock, path):
    if not _validate_path(path):
        _send_response(sock, "403 Forbidden", "text/html", _error_html(403, "Invalid path"))
        return
    try:
        st = os.stat(path)
        size = st[6]
    except:
        _send_response(sock, "404 Not Found", "text/html", _error_html(404, "Not found"))
        return
    ct = _content_type(path)
    hdr = "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(ct, size)
    sock.send(hdr.encode("utf-8"))
    try:
        with open(path, "rb") as f:
            while True:
                buf = bytearray(BUFFER_SIZE)
                n = f.readinto(buf)
                if n == 0:
                    break
                sock.send(bytes(buf[:n]))
    except:
        pass


def _handle_upload(sock, headers, body, query, add_log):
    ct = headers.get(b"content-type", b"").decode("utf-8", "ignore")
    if "boundary=" not in ct:
        _send_response(sock, "400 Bad Request", "text/html", _error_html(400, "No boundary"))
        return
    boundary = ct.split("boundary=")[1].split(";")[0].strip().strip('"').strip("'")
    boundary_bytes = ("--" + boundary).encode("utf-8")

    idx = body.find(boundary_bytes)
    if idx < 0:
        _send_response(sock, "400 Bad Request", "text/html", _error_html(400, "Invalid multipart"))
        return

    pos = idx + len(boundary_bytes)
    if body[pos:pos+2] == b"\r\n":
        pos += 2

    header_end = body.find(b"\r\n\r\n", pos)
    if header_end < 0:
        _send_response(sock, "400 Bad Request", "text/html", _error_html(400, "No part headers"))
        return

    part_headers = body[pos:header_end].decode("utf-8", "ignore")
    pos = header_end + 4

    filename = None
    for line in part_headers.split("\r\n"):
        low = line.lower()
        if "filename=" in low:
            start = line.find('filename="')
            if start >= 0:
                start += 10
                end = line.find('"', start)
                if end > start:
                    filename = line[start:end]
                    break
            start = line.find("filename='")
            if start >= 0:
                start += 10
                end = line.find("'", start)
                if end > start:
                    filename = line[start:end]
                    break

    if not filename:
        _send_response(sock, "400 Bad Request", "text/html", _error_html(400, "No filename"))
        return

    filename = filename.replace("/", "").replace("\\", "").replace("..", "")
    if not filename:
        _send_response(sock, "400 Bad Request", "text/html", _error_html(400, "Bad filename"))
        return

    end_boundary1 = b"\r\n" + boundary_bytes
    end_boundary2 = boundary_bytes
    end_idx = body.find(end_boundary1, pos)
    if end_idx < 0:
        end_idx = body.find(end_boundary2, pos)
    if end_idx >= 0:
        file_data = body[pos:end_idx]
    else:
        file_data = body[pos:]
    if file_data.endswith(b"\r\n"):
        file_data = file_data[:-2]

    save_path = query.get("path", "/sd")
    if not _validate_path(save_path):
        _send_response(sock, "403 Forbidden", "text/html", _error_html(403, "Invalid path"))
        return

    full_path = save_path + "/" + filename
    try:
        with open(full_path, "wb") as f:
            f.write(file_data)
        add_log("UP " + filename[:20])
        _send_redirect(sock, "/browse?path=" + _quote(save_path))
    except Exception as e:
        _send_response(sock, "500 Error", "text/html", _error_html(500, str(e)))


def _handle_http(client, addr, ap_ip, add_log):
    req = _parse_request(client)
    if not req:
        client.close()
        return
    method, path, headers, body = req
    add_log(method + " " + path[:24])
    pp, query = _parse_path(path)

    # Captive portal probes
    if pp in CAPTIVE_PATHS:
        _send_response(client, "200 OK", "text/html", _captive_html(ap_ip))
        client.close()
        return

    if pp == "/":
        _send_redirect(client, "http://" + ap_ip + "/browse?path=/sd")
    elif pp == "/browse":
        target = query.get("path", "/sd")
        if not _validate_path(target):
            _send_response(client, "403 Forbidden", "text/html", _error_html(403, "Invalid path"))
        else:
            html = _list_dir_html(target, ap_ip)
            _send_response(client, "200 OK", "text/html", html)
    elif pp in ("/file", "/img"):
        target = query.get("path", "/sd")
        _serve_file(client, target)
    elif pp == "/upload" and method == "POST":
        _handle_upload(client, headers, body, query, add_log)
    else:
        _send_response(client, "404 Not Found", "text/html", _error_html(404, "Not found"))

    client.close()


def run(display, touch, keyboard, W, H):
    batt = BatteryMonitor()
    keyboard = get_keyboard()

    # --- Read settings ---
    ssid = os.getenv("WEBSERVER_AP_SSID", "GR3ML1N-Web")
    password = os.getenv("WEBSERVER_AP_PASSWORD", "gr3ml1n123")

    # --- UI Setup ---
    sc = displayio.Group()
    _, title_right = ui.make_title_bar(sc, "WEB SERVER", "",
        time_str=timekeeper.now_str(),
        battery_str="{:.1f}V".format(batt.voltage) if batt.voltage > 0.1 else "")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    status_y = ui.CONTENT_Y + 4

    # Toggle button on right side
    btn_x = W - 84
    btn_y = status_y
    btn_w = 80
    btn_h = 28
    _, toggle_lbl = ui.make_button(sc, btn_x, btn_y, btn_w, btn_h,
                                   "START", bg_color=ui.C_BG_PANEL, text_color=ui.C_GREEN_HI)
    ui.make_border(sc, btn_x, btn_y, btn_w, btn_h, ui.C_GREEN_MID)

    ap_lbl = label.Label(terminalio.FONT, text="AP: " + ssid[:14], color=ui.C_GREEN_HI, scale=1)
    ap_lbl.anchor_point = (0.0, 0.0)
    ap_lbl.anchored_position = (4, status_y)
    sc.append(ap_lbl)

    status_lbl = label.Label(terminalio.FONT, text="OFFLINE", color=ui.C_RED_DIM, scale=1)
    status_lbl.anchor_point = (1.0, 0.5)
    status_lbl.anchored_position = (btn_x - 4, btn_y + btn_h // 2)
    sc.append(status_lbl)

    ip_lbl = label.Label(terminalio.FONT, text="IP: --", color=ui.C_GREEN_MID, scale=1)
    ip_lbl.anchor_point = (0.0, 0.0)
    ip_lbl.anchored_position = (4, status_y + 16)
    sc.append(ip_lbl)

    port_lbl = label.Label(terminalio.FONT, text="Ports: 80, 666", color=ui.C_GREEN_MID, scale=1)
    port_lbl.anchor_point = (0.0, 0.0)
    port_lbl.anchored_position = (4, status_y + 32)
    sc.append(port_lbl)

    pwd_lbl = label.Label(terminalio.FONT, text="PWD: " + password[:14], color=ui.C_AMBER, scale=1)
    pwd_lbl.anchor_point = (0.0, 0.0)
    pwd_lbl.anchored_position = (4, status_y + 48)
    sc.append(pwd_lbl)

    log_title = label.Label(terminalio.FONT, text="LOG:", color=ui.C_GREEN, scale=1)
    log_title.anchor_point = (0.0, 0.0)
    log_title.anchored_position = (4, status_y + 72)
    sc.append(log_title)

    log_lines = [""] * MAX_LOG
    log_lbls = []
    for i in range(MAX_LOG):
        l = label.Label(terminalio.FONT, text="", color=ui.C_GREEN_DIM, scale=1)
        l.anchor_point = (0.0, 0.0)
        l.anchored_position = (4, status_y + 88 + i * 14)
        sc.append(l)
        log_lbls.append(l)

    ui.make_footer(sc, "ESC or SWIPE UP to quit")
    display.root_group = sc

    def _add_log(msg):
        log_lines.pop(0)
        log_lines.append(msg[:36])
        for i, lbl in enumerate(log_lbls):
            lbl.text = log_lines[i]

    # --- Server state ---
    server_on = False
    ap_ip = None
    pool = None
    ip_bytes = None
    dns_sock = None
    http80 = None
    http666 = None

    def _start_server():
        nonlocal ap_ip, pool, ip_bytes, dns_sock, http80, http666
        _add_log("Starting AP...")
        try:
            if not wifi.radio.enabled:
                wifi.radio.enabled = True
            try:
                wifi.radio.stop_station()
            except:
                pass
            wifi.radio.start_ap(ssid, password)
            time.sleep(1)
            try:
                ap_ip = str(wifi.radio.ipv4_address_ap)
            except:
                ap_ip = FALLBACK_IP
            ip_lbl.text = "IP: " + ap_ip
            _add_log("AP " + ap_ip)
        except Exception as e:
            ip_lbl.text = "ERR: " + str(e)[:14]
            _add_log("AP FAIL")
            return False

        pool = socketpool.SocketPool(wifi.radio)
        ip_bytes = _ap_ip_bytes(ap_ip)

        try:
            dns_sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
            dns_sock.bind((ap_ip, DNS_PORT))
            dns_sock.settimeout(0.1)
            _add_log("DNS OK")
        except Exception as e:
            _add_log("DNS ERR")
            dns_sock = None

        try:
            http80 = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
            http80.bind((ap_ip, HTTP_PORT_80))
            http80.listen(1)
            http80.settimeout(0.1)
            _add_log("HTTP:80 OK")
        except Exception as e:
            _add_log("HTTP80 ERR")
            http80 = None

        try:
            http666 = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
            http666.bind((ap_ip, HTTP_PORT_666))
            http666.listen(1)
            http666.settimeout(0.1)
            _add_log("HTTP:666 OK")
        except Exception as e:
            _add_log("HTTP666 ERR")
            http666 = None

        if not http80 and not http666:
            _add_log("NO HTTP!")
        return True

    def _stop_server():
        nonlocal dns_sock, http80, http666, ap_ip, pool, ip_bytes
        _add_log("Stopping...")
        for sock in (dns_sock, http80, http666):
            try:
                if sock:
                    sock.close()
            except:
                pass
        dns_sock = None
        http80 = None
        http666 = None
        try:
            wifi.radio.stop_ap()
        except:
            pass
        ap_ip = None
        pool = None
        ip_bytes = None
        ip_lbl.text = "IP: --"
        _add_log("Stopped")

    def _toggle():
        nonlocal server_on
        if server_on:
            _stop_server()
            server_on = False
            toggle_lbl.text = "START"
            toggle_lbl.color = ui.C_GREEN_HI
            status_lbl.text = "OFFLINE"
            status_lbl.color = ui.C_RED_DIM
        else:
            if _start_server():
                server_on = True
                toggle_lbl.text = "STOP"
                toggle_lbl.color = ui.C_RED_DIM
                status_lbl.text = "ONLINE"
                status_lbl.color = ui.C_GREEN_HI
            else:
                status_lbl.text = "FAILED"
                status_lbl.color = ui.C_AMBER

    # Auto-start on launch
    _toggle()

    running = True
    fd = False
    sx = sy = lx = ly = 0
    last_clock = 0

    # --- Main Loop ---
    while running:
        now = time.monotonic()
        if now - last_clock >= 5.0:
            last_clock = now
            try:
                title_right.text = timekeeper.now_str()
            except:
                pass

        if server_on:
            # DNS
            if dns_sock:
                try:
                    data, addr = dns_sock.recvfrom(512)
                    resp = _build_dns_response(data, ip_bytes)
                    if resp:
                        dns_sock.sendto(resp, addr)
                except OSError:
                    pass
                except Exception as e:
                    pass

            # HTTP 80
            if http80:
                try:
                    client, addr = http80.accept()
                    client.settimeout(3.0)
                    _handle_http(client, addr, ap_ip, _add_log)
                except OSError:
                    pass
                except Exception as e:
                    _add_log("H80ERR " + str(e)[:8])

            # HTTP 666
            if http666:
                try:
                    client, addr = http666.accept()
                    client.settimeout(3.0)
                    _handle_http(client, addr, ap_ip, _add_log)
                except OSError:
                    pass
                except Exception as e:
                    _add_log("H666ERR " + str(e)[:8])

        # Keyboard
        if keyboard:
            kbd = keyboard.poll()
            if kbd["escape"]:
                running = False

        # Touch
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
            if g:
                if g[0] == "TAP":
                    if (btn_x <= sx <= btn_x + btn_w and
                        btn_y <= sy <= btn_y + btn_h):
                        _toggle()
                elif g[0] == "SWIPE UP":
                    running = False

    # --- Cleanup ---
    _stop_server()

    display.root_group = displayio.Group()
    del sc
    gc.collect()
