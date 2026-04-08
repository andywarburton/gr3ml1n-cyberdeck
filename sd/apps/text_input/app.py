# apps/text_input/app.py
# CyberDeck app: Text Input | portrait 240x320
# UART keyboard input only

import displayio
import terminalio
import time
import os
import gc
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

try:
    from uart_keyboard import UartKeyboard
    _HAS_UART_KB = True
except Exception:
    _HAS_UART_KB = False

_DATA_DIR = "/sd/apps/text_input/data"
_MAX_CHARS = 36


# ── File helpers ──────────────────────────────────────────────────────────────

def _ensure_dir():
    try:
        os.listdir(_DATA_DIR)
    except OSError:
        try:
            os.mkdir(_DATA_DIR)
        except OSError:
            pass


def _list_files():
    try:
        return sorted(f for f in os.listdir(_DATA_DIR) if f.endswith(".txt"))
    except OSError:
        return []


def _next_auto_name(existing):
    used = set()
    for f in existing:
        if f.startswith("note_") and f.endswith(".txt"):
            try:
                used.add(int(f[5:8]))
            except (ValueError, IndexError):
                pass
    n = 1
    while n in used:
        n += 1
    return "note_{:03d}.txt".format(n)


def _read(path):
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return ""


def _write(path, text):
    try:
        with open(path, "w") as fh:
            fh.write(text)
        return True
    except OSError as e:
        print("text_input: write error:", e)
        return False


def _wrap(text, w=_MAX_CHARS):
    out = []
    for raw in text.split("\n"):
        if not raw:
            out.append("")
        else:
            while len(raw) > w:
                out.append(raw[:w])
                raw = raw[w:]
            out.append(raw)
    return out


# ── List screen ──────────────────────────────────────────────────────────────

def _list_screen(display, touch, W, H):
    page = 0

    while True:
        files = _list_files()
        n_pages = max(1, (len(files) + 4) // 5)
        if page >= n_pages:
            page = n_pages - 1
        vis = files[page * 5: page * 5 + 5]

        sc = displayio.Group()
        ui.make_title_bar(sc, "SYS:TEXT INPUT", "v1.0")
        ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

        NEW_Y = ui.CONTENT_Y
        NEW_H = 44
        ui.solid_rect(sc, 4, NEW_Y, W - 8, NEW_H, ui.C_BG_PANEL)
        ui.make_border(sc, 4, NEW_Y, W - 8, NEW_H, ui.C_GREEN_MID)
        nl = label.Label(terminalio.FONT, text="+ NEW",
                         color=ui.C_GREEN_HI, scale=2)
        nl.anchor_point = (0.5, 0.5)
        nl.anchored_position = (W // 2, NEW_Y + NEW_H // 2)
        sc.append(nl)

        ROW_H = 38
        ROW_Y0 = NEW_Y + NEW_H + 3
        rows = []
        for i, fname in enumerate(vis):
            ry = ROW_Y0 + i * (ROW_H + 3)
            content = _read(_DATA_DIR + "/" + fname)
            preview = content.split("\n")[0][:26] if content else "(empty)"
            ui.solid_rect(sc, 4, ry, W - 8, ROW_H, ui.C_BG_PANEL)
            ui.solid_rect(sc, 4, ry, 3, ROW_H, ui.C_GREEN_MID)
            fl = label.Label(terminalio.FONT, text=fname[:-4].replace('_', ' ').upper(),
                             color=ui.C_GREEN_HI, scale=1)
            fl.anchor_point = (0.0, 0.0)
            fl.anchored_position = (10, ry + 4)
            sc.append(fl)
            pl = label.Label(terminalio.FONT, text=preview,
                             color=ui.C_GREEN_MID, scale=1)
            pl.anchor_point = (0.0, 0.0)
            pl.anchored_position = (10, ry + 20)
            sc.append(pl)
            rows.append((ry, ry + ROW_H, fname))

        if n_pages > 1:
            pgl = label.Label(terminalio.FONT,
                text="< {}/{} >".format(page + 1, n_pages),
                color=ui.C_GREEN_DIM, scale=1)
            pgl.anchor_point = (0.5, 0.5)
            pgl.anchored_position = (W // 2, 278)
            sc.append(pgl)

        ui.make_footer(sc, "TAP=OPEN  ^ SWIPE UP=QUIT")
        display.root_group = sc

        fd = False
        sx = sy = lx = ly = 0
        result = None

        while result is None:
            x, y, tch = touch.read()
            time.sleep(0.04)
            if tch:
                lx, ly = x, y
                if not fd:
                    fd = True; sx, sy = x, y
            elif fd:
                fd = False
                g = classify_gesture(sx, sy, lx, ly, W, H,
                    swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
                if not g:
                    continue
                gk = g[0]
                if gk == "SWIPE UP":
                    result = ("quit",)
                elif gk == "SWIPE LEFT":
                    if page < n_pages - 1:
                        page += 1
                    result = "page"
                elif gk == "SWIPE RIGHT":
                    if page > 0:
                        page -= 1
                    result = "page"
                elif gk == "TAP":
                    if NEW_Y <= sy <= NEW_Y + NEW_H:
                        result = ("new",)
                    else:
                        for (r0, r1, fn) in rows:
                            if r0 <= sy <= r1:
                                result = ("edit", _DATA_DIR + "/" + fn)
                                break

        display.root_group = displayio.Group()
        del sc
        gc.collect()

        if result == "page":
            continue
        return result


# ── Editor ──────────────────────────────────────────────────────────────────

def _editor(display, touch, W, H, path):
    text = _read(path)
    name = path.split("/")[-1][:-4].replace('_', ' ').upper()

    sc = displayio.Group()
    ui.make_title_bar(sc, "TEXT INPUT:EDIT", name)
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    TY = [ui.CONTENT_Y + 2 + i * 14 for i in range(8)]
    tlbls = []
    for i in range(8):
        tl = label.Label(terminalio.FONT, text=" ", color=ui.C_GREEN, scale=1)
        tl.anchor_point = (0.0, 0.0)
        tl.anchored_position = (2, TY[i])
        sc.append(tl)
        tlbls.append(tl)

    IY = ui.CONTENT_Y + 120
    ui.solid_rect(sc, 0, IY - 1, W, 1, ui.C_GREEN_DIM)
    ui.solid_rect(sc, 0, IY, W, 18, ui.C_BG_PANEL)
    ui.solid_rect(sc, 0, IY + 18, W, 1, ui.C_GREEN_DIM)
    ilbl = label.Label(terminalio.FONT, text="> |", color=ui.C_GREEN_HI, scale=1)
    ilbl.anchor_point = (0.0, 0.5)
    ilbl.anchored_position = (2, IY + 9)
    sc.append(ilbl)

    SY = IY + 22
    slbl = label.Label(terminalio.FONT, text="0 chars", color=ui.C_GREEN_DIM, scale=1)
    slbl.anchor_point = (0.0, 0.5)
    slbl.anchored_position = (2, SY)
    sc.append(slbl)

    ui.make_footer(sc, "^ SWIPE UP = SAVE & QUIT")
    display.root_group = sc

    def _refresh():
        all_lines = _wrap(text)
        disp = all_lines[-8:] if len(all_lines) > 8 else all_lines
        for i in range(8):
            tlbls[i].text = (disp[i][:36] if i < len(disp) else "") or " "
        last = all_lines[-1] if all_lines else ""
        ilbl.text = ("> " + last + "|")[:38]
        slbl.text = "{} chars".format(len(text))

    _refresh()

    # Init UART keyboard
    uart_kb = None
    if _HAS_UART_KB:
        try:
            uart_kb = UartKeyboard()
            slbl.text = "0 chars [UART OK]"
        except Exception:
            slbl.text = "0 chars [NO UART]"

    fd = False
    sx = sy = lx = ly = 0

    while True:
        # Poll UART first (higher priority)
        if uart_kb:
            result = uart_kb.poll()
            if result['char']:
                text += result['char']
                _refresh()
            elif result['delete']:
                if text:
                    text = text[:-1]
                    _refresh()
            elif result['enter']:
                text += "\n"
                _refresh()

        # Check touch (swipe up to quit)
        x, y, tch = touch.read()

        if tch:
            lx, ly = x, y
            if not fd:
                fd = True
                sx, sy = x, y
        elif fd:
            fd = False
            g = classify_gesture(sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN)
            if g and g[0] == "SWIPE UP":
                if text:
                    slbl.text = "SAVING..."
                    slbl.color = ui.C_AMBER
                    ok = _write(path, text)
                    slbl.text = "SAVED!" if ok else "SAVE ERR"
                    slbl.color = ui.C_GREEN_HI if ok else ui.C_RED
                    time.sleep(1.0)
                if uart_kb:
                    uart_kb.deinit()
                break

    display.root_group = displayio.Group()
    del sc
    gc.collect()


# ── Entry point ──────────────────────────────────────────────────────────────

def run(display, touch, W, H):
    _ensure_dir()
    while True:
        res = _list_screen(display, touch, W, H)
        if res[0] == "quit":
            break
        elif res[0] == "new":
            fname = _next_auto_name(_list_files())
            _editor(display, touch, W, H, _DATA_DIR + "/" + fname)
        elif res[0] == "edit":
            _editor(display, touch, W, H, res[1])
    display.root_group = displayio.Group()
