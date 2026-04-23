# apps/ai_chat/app.py
# CyberDeck app: AI Chat | portrait 240x320

import displayio
import terminalio
import time
import gc
import os
import json
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui
from battery_monitor import BatteryMonitor
import timekeeper
from uart_keyboard import get_keyboard

_PRESET = "@preset/free-chat-agents"
LINE_H = 14
HISTORY_LINES = 15


def _connect_wifi():
    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    pwd = os.getenv("CIRCUITPY_WIFI_PASSWORD") or ""
    if not ssid:
        return None, "NO SSID"
    try:
        import wifi
        if wifi.radio.ipv4_address:
            return wifi.radio, "OK"
        wifi.radio.connect(ssid, pwd)
        for _ in range(10):
            if wifi.radio.ipv4_address:
                return wifi.radio, "OK"
            time.sleep(1)
        return None, "TIMEOUT"
    except Exception as e:
        return None, str(e)


def _send_request(radio, api_key, model, messages):
    if not radio:
        print("AI: ERROR: No WiFi radio")
        return None, "No WiFi"
    print("AI: Building request...")
    print("AI: Messages count:", len(messages))
    for i, m in enumerate(messages):
        print("AI: msg[", i, "] role=", m.get("role"), "content_len=", len(m.get("content", "")))
    body = json.dumps({"model": model, "messages": list(messages)})
    body_bytes = body.encode('utf-8')
    print("AI: Body chars:", len(body), "bytes:", len(body_bytes))
    print("AI: Body preview:", body[:200])
    req = (
        "POST /api/v1/chat/completions HTTP/1.1\r\n"
        "Host: openrouter.ai\r\n"
        "Authorization: Bearer " + api_key + "\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + str(len(body_bytes)) + "\r\n"
        "HTTP-Referer: https://gr3ml1n.local\r\n"
        "X-Title: GR3ML1N\r\n"
        "Connection: close\r\n\r\n" + body
    )
    try:
        import socketpool, ssl
        print("AI: Creating socketpool...")
        pool = socketpool.SocketPool(radio)
        print("AI: Getting addrinfo...")
        addr = pool.getaddrinfo("openrouter.ai", 443)[0][-1]
        print("AI: Address:", addr)
        print("AI: Creating raw socket...")
        raw = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        raw.settimeout(30)
        print("AI: Wrapping SSL...")
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(raw, server_hostname="openrouter.ai")
        print("AI: Connecting...")
        sock.connect(addr)
        print("AI: Connected!")
        print("AI: Sending request...")
        sent = sock.send(req.encode())
        print("AI: Sent", sent, "bytes")
        print("AI: Reading response...")
        resp = b""
        while True:
            buf = bytearray(512)
            n = sock.recv_into(buf)
            if not n:
                print("AI: Connection closed by server")
                break
            resp += buf[:n]
            print("AI: Got chunk, total:", len(resp))
        sock.close()
        print("AI: Total response length:", len(resp))
        if not resp:
            print("AI: ERROR: Empty response")
            return None, "Empty response"
        bs = resp.find(b"\r\n\r\n")
        if bs < 0:
            print("AI: ERROR: No header/body separator")
            return None, "Bad response"
        bs += 4
        raw_body = resp[bs:]
        print("AI: Raw body length:", len(raw_body))
        if b"Transfer-Encoding: chunked" in resp[:bs]:
            print("AI: Decoding chunked response...")
            decoded = b""
            pos = 0
            while pos < len(raw_body):
                cr = raw_body.find(b"\r\n", pos)
                if cr < 0:
                    break
                hx = raw_body[pos:cr].decode("utf-8", "ignore").strip()
                if not hx:
                    pos = cr + 2
                    continue
                try:
                    cs = int(hx, 16)
                except ValueError:
                    break
                if cs == 0:
                    break
                pos = cr + 2
                decoded += raw_body[pos:pos + cs]
                pos += cs + 2
            raw_body = decoded
            print("AI: Decoded body length:", len(raw_body))
        if raw_body.startswith(b"<"):
            print("AI: ERROR: Got HTML redirect/error")
            return None, "HTML error"
        print("AI: Body preview:", raw_body[:200])
        try:
            data = json.loads(raw_body.decode("utf-8", "ignore"))
        except Exception as e:
            print("AI: JSON parse error:", e)
            return None, "JSON: " + str(e)
        print("AI: Parsed JSON keys:", list(data.keys()))
        if "error" in data:
            print("AI: API error:", data["error"])
            return None, str(data["error"])
        if "choices" not in data:
            print("AI: ERROR: No choices in response")
            return None, "No choices"
        content = data["choices"][0]["message"].get("content")
        model_used = data.get("model", "unknown")
        print("AI: Success, model:", model_used, "content len:", len(content) if content else 0)
        return {
            "content": content,
            "model": model_used
        }, None
    except Exception as e:
        print("AI: Request exception:", type(e).__name__, e)
        return None, str(e)


def _wrap_text(text, max_chars=38):
    text = text.replace("\n", " ")
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > max_chars:
            lines.append(current)
            current = word
        else:
            current = current + " " + word if current else word
    if current:
        lines.append(current)
    return lines


def _build_history_lines(history, max_lines=200):
    flat = []
    for idx, (text, is_user) in enumerate(history):
        color = ui.C_GREEN_MID if is_user else ui.C_GREEN_HI
        # Keep final prefixed lines under 36 chars so they never touch the edge
        raw_max = 32 if is_user else 34
        wrapped_lines = _wrap_text(text, max_chars=raw_max)
        for j, wrapped in enumerate(wrapped_lines):
            if is_user and j == 0:
                line_text = "> " + wrapped
            elif is_user:
                line_text = "  " + wrapped
            else:
                line_text = "  " + wrapped
            flat.append((line_text, color, is_user))
        # Spacer between messages
        if idx < len(history) - 1:
            flat.append(("", ui.C_GREEN_DIM, False))
    return flat


def _render_history(history_lbls, flat_lines, scroll_offset, max_visible, W):
    for i in range(max_visible):
        idx = scroll_offset + i
        lbl = history_lbls[i]
        if idx < len(flat_lines):
            text, color, is_user = flat_lines[idx]
            lbl.text = text
            lbl.color = color
            if is_user:
                lbl.anchor_point = (1.0, 0.0)
                lbl.anchored_position = (W - 4, lbl.anchored_position[1])
            else:
                lbl.anchor_point = (0.0, 0.0)
                lbl.anchored_position = (4, lbl.anchored_position[1])
        else:
            lbl.text = ""


def run(display, touch, keyboard, W, H):
    batt = BatteryMonitor()
    keyboard = get_keyboard()
    print("AI: App started")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("AI: ERROR: No API key found")
        sc = displayio.Group()
        ui.make_title_bar(sc, "AI CHAT", "v1.0",
            time_str=timekeeper.now_str(),
            battery_str="{:.1f}V".format(batt.voltage) if batt.voltage > 0.1 else "")
        ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)
        lbl = label.Label(terminalio.FONT, text="ERROR: OPENROUTER_API_KEY not set",
                          color=ui.C_AMBER, scale=1)
        lbl.anchor_point = (0.5, 0.5)
        lbl.anchored_position = (W // 2, H // 2)
        sc.append(lbl)
        ui.make_footer(sc, "ESC to quit")
        display.root_group = sc
        while True:
            if keyboard.poll()["escape"]:
                break
            time.sleep(0.05)
        display.root_group = displayio.Group()
        return

    radio, status = _connect_wifi()
    if radio:
        print("AI: WiFi OK:", status)
    if not radio:
        sc = displayio.Group()
        ui.make_title_bar(sc, "AI CHAT", "v1.0",
            time_str=timekeeper.now_str(),
            battery_str="{:.1f}V".format(batt.voltage) if batt.voltage > 0.1 else "")
        ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)
        lbl = label.Label(terminalio.FONT, text="ERROR: WiFi " + status,
                          color=ui.C_AMBER, scale=1)
        lbl.anchor_point = (0.5, 0.5)
        lbl.anchored_position = (W // 2, H // 2)
        sc.append(lbl)
        ui.make_footer(sc, "ESC to quit")
        display.root_group = sc
        while True:
            if keyboard.poll()["escape"]:
                break
            time.sleep(0.05)
        display.root_group = displayio.Group()
        return

    messages = []
    history = []
    flat_history = []
    scroll_offset = 0
    model_used = None

    INPUT_AREA_H = 40
    INPUT_Y = ui.FOOTER_Y - INPUT_AREA_H - 2
    SEPARATOR_Y = INPUT_Y - 3
    STATUS_Y = SEPARATOR_Y - 10
    HISTORY_TOP = ui.CONTENT_Y + 2

    sc = displayio.Group()
    _, title_right = ui.make_title_bar(sc, "AI CHAT", "ready",
        time_str=timekeeper.now_str(),
        battery_str="{:.1f}V".format(batt.voltage) if batt.voltage > 0.1 else "")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    history_lbls = []
    for i in range(HISTORY_LINES):
        l = label.Label(terminalio.FONT, text="", color=ui.C_GREEN_DIM, scale=1)
        l.anchor_point = (0.0, 0.0)
        l.anchored_position = (4, HISTORY_TOP + i * LINE_H)
        sc.append(l)
        history_lbls.append(l)

    status_lbl = label.Label(terminalio.FONT, text="WiFi OK",
                             color=ui.C_GREEN_MID, scale=1)
    status_lbl.anchor_point = (0.5, 1.0)
    status_lbl.anchored_position = (W // 2, STATUS_Y)
    sc.append(status_lbl)

    ui.solid_rect(sc, 4, SEPARATOR_Y, W - 8, 1, ui.C_GREEN_MID)

    input_lbl = label.Label(terminalio.FONT, text=">", color=ui.C_GREEN_HI, scale=1)
    input_lbl.anchor_point = (0.0, 0.0)
    input_lbl.anchored_position = (4, INPUT_Y + 2)
    sc.append(input_lbl)

    send_btn_x = W - 80
    send_btn_y = INPUT_Y + 4
    send_btn_w = 76
    send_btn_h = 28
    _, send_lbl = ui.make_button(sc, send_btn_x, send_btn_y, send_btn_w, send_btn_h,
                               "SEND", bg_color=ui.C_BG_PANEL, text_color=ui.C_GREEN_HI)
    ui.make_border(sc, send_btn_x, send_btn_y, send_btn_w, send_btn_h, ui.C_GREEN_MID)

    ui.make_footer(sc, "ESC=quit  ^v=scroll")
    display.root_group = sc

    input_text = ""
    thinking = False
    fd = False
    sx = sy = lx = ly = 0

    def _update_scroll(new_offset):
        nonlocal scroll_offset
        max_scroll = max(0, len(flat_history) - HISTORY_LINES)
        scroll_offset = max(0, min(new_offset, max_scroll))
        _render_history(history_lbls, flat_history, scroll_offset, HISTORY_LINES, W)

    def _scroll_to_bottom():
        _update_scroll(max(0, len(flat_history) - HISTORY_LINES))

    def _poll_stop():
        """Check if user pressed ESC or tapped STOP button. Returns True if stop requested."""
        if keyboard:
            kbd = keyboard.poll()
            if kbd["escape"]:
                print("AI: ESC pressed during response")
                return True
        x, y, tch = touch.read()
        if tch and (send_btn_x <= x <= send_btn_x + send_btn_w and
                    send_btn_y <= y <= send_btn_y + send_btn_h):
            print("AI: STOP button tapped")
            return True
        return False

    def _do_send():
        nonlocal thinking, input_text, messages, history, flat_history
        nonlocal scroll_offset, model_used
        if not input_text or thinking:
            return False
        print("AI: --- SEND START ---")
        thinking = True
        status_lbl.text = "Thinking..."
        send_lbl.text = "STOP"
        send_lbl.color = ui.C_GREEN_DIM
        display.root_group = displayio.Group()
        display.root_group = sc
        gc.collect()
        print("AI: GC free:", gc.mem_free())

        user_msg = input_text
        messages.append({"role": "user", "content": user_msg})
        history.append((user_msg, True))
        input_text = ""
        input_lbl.text = ">"
        flat_history = _build_history_lines(history)
        _scroll_to_bottom()

        model_to_use = model_used if model_used else _PRESET
        print("AI: Using model:", model_to_use)
        result, err = _send_request(radio, api_key, model_to_use, messages)

        if err:
            print("AI: API error:", err)
            status_lbl.text = err[:28]
            messages.pop()
            history.pop()
            thinking = False
            send_lbl.color = ui.C_GREEN_HI
            flat_history = _build_history_lines(history)
            _scroll_to_bottom()
            display.root_group = displayio.Group()
            display.root_group = sc
            print("AI: --- SEND DONE (error) ---")
            return True

        answer = result.get("content")
        print("AI: content type:", type(answer), "len:", len(answer) if answer else 0)
        if answer is None:
            print("AI: ERROR: content is None")
            status_lbl.text = "ERROR: Empty response"
            messages.pop()
            history.pop()
            thinking = False
            send_lbl.color = ui.C_GREEN_HI
            flat_history = _build_history_lines(history)
            _scroll_to_bottom()
            display.root_group = displayio.Group()
            display.root_group = sc
            print("AI: --- SEND DONE (null) ---")
            return True

        # Lock to the resolved model for the rest of the conversation
        if model_used is None:
            model_used = result.get("model", "unknown")
            title_right.text = model_used.split("/")[-1][:12]
            print("AI: Locked to model:", model_used)

        messages.append({"role": "assistant", "content": answer})
        history.append(("", False))
        flat_history = _build_history_lines(history)
        _scroll_to_bottom()

        # Normalize whitespace for display typing animation
        display_answer = answer.replace("\r\n", "\n").replace("\n", " ").replace("\u00A0", " ").replace("\t", " ")
        words = display_answer.split()
        current_text = ""
        batch_size = 5
        stop_requested = False
        print("AI: Typing", len(words), "words...")
        print("AI: First 80 chars:", display_answer[:80])
        for i in range(0, len(words), batch_size):
            if _poll_stop():
                stop_requested = True
                break
            chunk = words[i:i + batch_size]
            joined = " ".join(chunk)
            if current_text:
                current_text = current_text + " " + joined
            else:
                current_text = joined
            history[-1] = (current_text, False)
            flat_history = _build_history_lines(history)
            _scroll_to_bottom()
            display.root_group = displayio.Group()
            display.root_group = sc
            status_lbl.text = "Typing " + str(min(i + batch_size, len(words))) + "/" + str(len(words))
            # Short sleep with polling
            for _ in range(5):
                if _poll_stop():
                    stop_requested = True
                    break
                time.sleep(0.001)
            if stop_requested:
                break

        if stop_requested:
            # Truncate the stored message to what was shown
            final_text = history[-1][0]
            messages[-1]["content"] = final_text
            history[-1] = (final_text, False)
            flat_history = _build_history_lines(history)
            _scroll_to_bottom()
            status_lbl.text = "Stopped."
            print("AI: Response stopped by user")
        else:
            # Store final full answer
            history[-1] = (answer, False)
            flat_history = _build_history_lines(history)
            _scroll_to_bottom()
            status_lbl.text = "Done."

        thinking = False
        send_lbl.text = "SEND"
        send_lbl.color = ui.C_GREEN_HI
        display.root_group = displayio.Group()
        display.root_group = sc
        print("AI: --- SEND DONE ---")
        return True

    while True:
        if keyboard:
            kbd = keyboard.poll()
            if kbd["escape"]:
                break
            if not thinking:
                if kbd["enter"] and input_text:
                    _do_send()
                elif kbd["delete"]:
                    input_text = input_text[:-1]
                    input_lbl.text = ">" + input_text
                elif kbd["char"]:
                    input_text += kbd["char"]
                    input_lbl.text = ">" + input_text
                elif kbd["up"]:
                    _update_scroll(scroll_offset - 1)
                elif kbd["down"]:
                    _update_scroll(scroll_offset + 1)

        x, y, tch = touch.read()
        time.sleep(0.05)

        if tch:
            lx, ly = x, y
            if not fd:
                fd = True
                sx, sy = x, y
        elif fd:
            fd = False
            g = classify_gesture(sx, sy, lx, ly, W, H,
                               swipe_edge=ui.SWIPE_EDGE,
                               swipe_min_dist=ui.SWIPE_MIN)
            if g:
                if g[0] == "TAP":
                    if (send_btn_x <= sx <= send_btn_x + send_btn_w and
                        send_btn_y <= sy <= send_btn_y + send_btn_h):
                        if not thinking:
                            _do_send()
                elif g[0] == "SWIPE UP" and not thinking:
                    _update_scroll(scroll_offset + 1)
                elif g[0] == "SWIPE DOWN" and not thinking:
                    _update_scroll(scroll_offset - 1)

    display.root_group = displayio.Group()
    del sc
    gc.collect()