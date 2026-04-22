# apps/notes/app.py
# CyberDeck app: Notes | portrait 240x320
# T9-style text input; notes stored in /sd/apps/notes/data/

import displayio
import terminalio
import time
import os
import gc
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

_DATA_DIR   = "/sd/apps/notes/data"
_T9_TIMEOUT = 0.8

# T9 mapping: key_id -> chars cycled on repeated presses
_T9 = {
    "1": ".,!?-",
    "2": "ABC", "3": "DEF",
    "4": "GHI", "5": "JKL", "6": "MNO",
    "7": "PQRS", "8": "TUV", "9": "WXYZ",
}

# Keyboard layout: (key_id, top_label, bottom_chars)
_KB_ROWS = [
    [("1", "1", ".,!?"),  ("2", "2", "ABC"),  ("3", "3", "DEF")],
    [("4", "4", "GHI"),   ("5", "5", "JKL"),  ("6", "6", "MNO")],
    [("7", "7", "PQRS"),  ("8", "8", "TUV"),  ("9", "9", "WXYZ")],
    [("DEL", "DEL", ""),  ("0", "0", "SPC"),  ("ENT", "ENT", "")],
]
_KB_Y  = [115, 161, 207, 253]
_KB_X  = [1, 81, 161]
_KEY_W = 78
_KEY_H = 44

_MAX_NAME = 14    # max chars in a note name (fits scale=2 display)
_MAX_CHARS = 36   # chars per wrapped text line


# ── File helpers ──────────────────────────────────────────────────────────────

def _ensure_dir():
    try:
        os.listdir(_DATA_DIR)
    except OSError:
        try:
            os.mkdir(_DATA_DIR)
        except OSError:
            pass


def _list_notes():
    try:
        return sorted(f for f in os.listdir(_DATA_DIR) if f.endswith(".txt"))
    except OSError:
        return []


def _sanitize(s):
    """Convert T9 name to a safe filename stem (no extension)."""
    out = []
    for ch in s.lower():
        if ('a' <= ch <= 'z') or ('0' <= ch <= '9'):
            out.append(ch)
        elif ch == ' ':
            out.append('_')
    stem = ''.join(out).strip('_')[:20]
    return stem or None


def _unique_name(stem, existing):
    """Return stem.txt (or stem_2.txt etc.) not already in existing set."""
    existing_set = set(existing)
    candidate = stem + ".txt"
    if candidate not in existing_set:
        return candidate
    n = 2
    while True:
        candidate = "{}_{}.txt".format(stem, n)
        if candidate not in existing_set:
            return candidate
        n += 1


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


def _display_name(fname):
    """Pretty display name from filename: 'my_note.txt' -> 'MY NOTE'"""
    return fname[:-4].replace('_', ' ').upper()


def _read(path):
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return ""


def _write(path, text):
    """Write text to path. Returns True on success."""
    try:
        with open(path, "w") as fh:
            fh.write(text)
        return True
    except OSError as e:
        print("notes: write error:", e)
        return False


def _preview(text, n=26):
    for ln in text.split("\n"):
        ln = ln.strip()
        if ln:
            return ln[:n]
    return "(empty)"


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


# ── Shared keyboard builder ───────────────────────────────────────────────────

def _build_keyboard(sc):
    """Append keyboard to scene. Returns list of (x0,y0,x1,y1,kid,pal)."""
    ui.solid_rect(sc, 0, 113, ui.W, 1, ui.C_GREEN_MID)
    key_areas = []
    for ri, row in enumerate(_KB_ROWS):
        for ci, (kid, top, btm) in enumerate(row):
            kx  = _KB_X[ci]
            ky  = _KB_Y[ri]
            pal = ui.solid_rect(sc, kx, ky, _KEY_W, _KEY_H, ui.C_BG_PANEL)
            ui.make_border(sc, kx, ky, _KEY_W, _KEY_H, ui.C_GREEN_DIM)
            if kid in ("DEL", "ENT"):
                kl = label.Label(terminalio.FONT, text=top,
                                 color=ui.C_GREEN_HI, scale=2)
                kl.anchor_point = (0.5, 0.5)
                kl.anchored_position = (kx + _KEY_W // 2, ky + _KEY_H // 2)
                sc.append(kl)
            else:
                kl = label.Label(terminalio.FONT, text=top,
                                 color=ui.C_GREEN_HI, scale=2)
                kl.anchor_point = (0.5, 0.0)
                kl.anchored_position = (kx + _KEY_W // 2, ky + 4)
                sc.append(kl)
                if btm:
                    bl = label.Label(terminalio.FONT, text=btm,
                                     color=ui.C_GREEN_DIM, scale=1)
                    bl.anchor_point = (0.5, 1.0)
                    bl.anchored_position = (kx + _KEY_W // 2, ky + _KEY_H - 4)
                    sc.append(bl)
            key_areas.append((kx, ky, kx + _KEY_W, ky + _KEY_H, kid, pal))
    return key_areas


def _run_t9_loop(display, touch, keyboard, W, H, scene, key_areas,
                 on_key, check_timeout, on_swipe_up):
    """
    Generic T9 input event loop.
    Calls on_key(kid, now) on key tap.
    Calls check_timeout(now) every loop.
    Calls on_swipe_up() and returns True when SWIPE UP or ESC detected.
    Returns False on any other exit (caller-driven via exception/break).
    """
    fl_pal  = None
    fl_time = 0.0
    fd = False
    sx = sy = lx = ly = 0

    while True:
        now = time.monotonic()
        check_timeout(now)
        if fl_pal and now >= fl_time:
            fl_pal[0] = ui.C_BG_PANEL
            fl_pal = None

        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                return on_swipe_up()

        x, y, tch = touch.read()
        time.sleep(0.03)

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
                return on_swipe_up()
            for (x0, y0, x1, y1, kid, kpal) in key_areas:
                if x0 <= sx <= x1 and y0 <= sy <= y1:
                    kpal[0] = ui.C_GREEN_MID
                    fl_pal = kpal
                    fl_time = now + 0.15
                    result = on_key(kid, now)
                    if result == "done":
                        return True
                    break


# ── Name entry screen ─────────────────────────────────────────────────────────

def _name_screen(display, touch, keyboard, W, H):
    """
    T9 name entry. Returns the entered name string (may be empty if user
    skipped with SWIPE UP or ESC immediately).
    """
    name   = ""
    p_key  = None
    p_idx  = 0
    p_time = 0.0

    sc = displayio.Group()
    ui.make_title_bar(sc, "NOTES:NAME", "")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    prompt = label.Label(terminalio.FONT, text="NAME YOUR NOTE",
                         color=ui.C_GREEN_MID, scale=1)
    prompt.anchor_point = (0.5, 0.5)
    prompt.anchored_position = (W // 2, 38)
    sc.append(prompt)

    # Name display bar
    NB_Y = 55
    ui.solid_rect(sc, 4, NB_Y - 1, W - 8, 1, ui.C_GREEN_DIM)
    ui.solid_rect(sc, 4, NB_Y, W - 8, 24, ui.C_BG_PANEL)
    ui.solid_rect(sc, 4, NB_Y + 24, W - 8, 1, ui.C_GREEN_DIM)
    nlbl = label.Label(terminalio.FONT, text="> |",
                       color=ui.C_GREEN_HI, scale=2)
    nlbl.anchor_point = (0.0, 0.5)
    nlbl.anchored_position = (8, NB_Y + 12)
    sc.append(nlbl)

    hint = label.Label(terminalio.FONT,
                       text="ENT or ^ SWIPE UP = CONFIRM",
                       color=ui.C_GREEN_DIM, scale=1)
    hint.anchor_point = (0.5, 0.5)
    hint.anchored_position = (W // 2, 96)
    sc.append(hint)

    key_areas = _build_keyboard(sc)
    ui.make_footer(sc, "ENT or ^ SWIPE UP = CONFIRM")
    display.root_group = sc

    def _commit():
        nonlocal name, p_key, p_idx, p_time
        if p_key and p_key in _T9:
            c = _T9[p_key]
            name += c[p_idx % len(c)]
            if len(name) > _MAX_NAME:
                name = name[:_MAX_NAME]
        p_key = None; p_idx = 0; p_time = 0.0

    def _refresh():
        pc = (_T9[p_key][p_idx % len(_T9[p_key])]
              if p_key and p_key in _T9 else "")
        # scale=2: 12px/char, bar is 232px wide, prefix "> " = 2 chars
        # max displayable = (232 // 12) - 3 = ~16, limit fine at _MAX_NAME=14
        nlbl.text = ("> " + name + pc + "|")

    _refresh()

    def _on_key(kid, now):
        nonlocal name, p_key, p_idx, p_time
        if kid == "DEL":
            if p_key:
                p_key = None; p_idx = 0; p_time = 0.0
            elif name:
                name = name[:-1]
        elif kid == "ENT":
            _commit()
            return "done"
        elif kid == "0":
            _commit()
            if len(name) < _MAX_NAME:
                name += " "
        else:
            if p_key == kid:
                p_idx += 1; p_time = now
            else:
                _commit()
                p_key = kid; p_idx = 0; p_time = now
        _refresh()
        return None

    def _on_timeout(now):
        if p_key and (now - p_time) >= _T9_TIMEOUT:
            _commit(); _refresh()

    def _on_swipe():
        _commit()
        return True

    _run_t9_loop(display, touch, keyboard, W, H, sc, key_areas,
                 _on_key, _on_timeout, _on_swipe)

    display.root_group = displayio.Group()
    del sc
    gc.collect()
    return name.strip()


# ── List screen ───────────────────────────────────────────────────────────────

def _list_screen(display, touch, W, H):
    """Returns ("new",) | ("edit", path) | ("quit",)"""
    page = 0

    while True:
        notes   = _list_notes()
        n_pages = max(1, (len(notes) + 4) // 5)
        if page >= n_pages:
            page = n_pages - 1
        vis = notes[page * 5: page * 5 + 5]

        sc = displayio.Group()
        ui.make_title_bar(sc, "SYS:NOTES", "v1.1")
        ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

        # NEW NOTE button
        NEW_Y = ui.CONTENT_Y
        NEW_H = 44
        ui.solid_rect(sc, 4, NEW_Y, W - 8, NEW_H, ui.C_BG_PANEL)
        ui.make_border(sc, 4, NEW_Y, W - 8, NEW_H, ui.C_GREEN_MID)
        nl = label.Label(terminalio.FONT, text="+ NEW NOTE",
                         color=ui.C_GREEN_HI, scale=2)
        nl.anchor_point = (0.5, 0.5)
        nl.anchored_position = (W // 2, NEW_Y + NEW_H // 2)
        sc.append(nl)

        # Note rows
        ROW_H  = 38
        ROW_Y0 = NEW_Y + NEW_H + 3
        rows = []
        for i, fname in enumerate(vis):
            ry  = ROW_Y0 + i * (ROW_H + 3)
            prv = _preview(_read(_DATA_DIR + "/" + fname))
            ui.solid_rect(sc, 4, ry, W - 8, ROW_H, ui.C_BG_PANEL)
            ui.solid_rect(sc, 4, ry, 3, ROW_H, ui.C_GREEN_MID)
            fl = label.Label(terminalio.FONT,
                             text=_display_name(fname),
                             color=ui.C_GREEN_HI, scale=1)
            fl.anchor_point = (0.0, 0.0)
            fl.anchored_position = (10, ry + 4)
            sc.append(fl)
            pl = label.Label(terminalio.FONT, text=prv,
                             color=ui.C_GREEN_MID, scale=1)
            pl.anchor_point = (0.0, 0.0)
            pl.anchored_position = (10, ry + 20)
            sc.append(pl)
            rows.append((ry, ry + ROW_H, fname))

        if n_pages > 1:
            pgl = label.Label(terminalio.FONT,
                text="< PAGE {}/{} >".format(page + 1, n_pages),
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


# ── Editor ─────────────────────────────────────────────────────────────────---

def _editor(display, touch, keyboard, W, H, path):
    """T9 editor. Saves on SWIPE UP or ESC. Shows save status before returning."""
    text   = _read(path)
    p_key  = None
    p_idx  = 0
    p_time = 0.0

    sc = displayio.Group()
    ui.make_title_bar(sc, "NOTES:EDIT", "")
    ui.make_scan_bg(sc, ui.CONTENT_Y, ui.CONTENT_H)

    # 4 committed text lines
    TY = [ui.CONTENT_Y + 2 + i * 14 for i in range(4)]
    tlbls = []
    for i in range(4):
        tl = label.Label(terminalio.FONT, text=" ",
                         color=ui.C_GREEN, scale=1)
        tl.anchor_point = (0.0, 0.0)
        tl.anchored_position = (2, TY[i])
        sc.append(tl)
        tlbls.append(tl)

    # Input bar
    IY = ui.CONTENT_Y + 60
    ui.solid_rect(sc, 0, IY - 1, W, 1, ui.C_GREEN_DIM)
    ui.solid_rect(sc, 0, IY, W, 18, ui.C_BG_PANEL)
    ui.solid_rect(sc, 0, IY + 18, W, 1, ui.C_GREEN_DIM)
    ilbl = label.Label(terminalio.FONT, text="> |",
                       color=ui.C_GREEN_HI, scale=1)
    ilbl.anchor_point = (0.0, 0.5)
    ilbl.anchored_position = (2, IY + 9)
    sc.append(ilbl)

    # Status bar
    SY = IY + 22
    slbl = label.Label(terminalio.FONT, text="0 chars",
                       color=ui.C_GREEN_DIM, scale=1)
    slbl.anchor_point = (0.0, 0.5)
    slbl.anchored_position = (2, SY)
    sc.append(slbl)

    key_areas = _build_keyboard(sc)
    ui.make_footer(sc, "ESC or SWIPE UP = SAVE & QUIT")
    display.root_group = sc

    def _commit():
        nonlocal text, p_key, p_idx, p_time
        if p_key and p_key in _T9:
            c = _T9[p_key]
            text += c[p_idx % len(c)]
        p_key = None; p_idx = 0; p_time = 0.0

    def _refresh():
        all_lines = _wrap(text)
        disp = all_lines[-4:] if len(all_lines) > 4 else all_lines
        for i in range(4):
            tlbls[i].text = (disp[i][:36] if i < len(disp) else "") or " "
        last = all_lines[-1] if all_lines else ""
        pc = (_T9[p_key][p_idx % len(_T9[p_key])]
              if p_key and p_key in _T9 else "")
        ilbl.text = ("> " + last + pc + "|")[:38]
        slbl.text = "{} chars".format(len(text))

    _refresh()

    saved = [False]   # mutable for closure

    def _on_key(kid, now):
        nonlocal text, p_key, p_idx, p_time
        if kid == "DEL":
            if p_key:
                p_key = None; p_idx = 0; p_time = 0.0
            elif text:
                text = text[:-1]
        elif kid == "ENT":
            _commit(); text += "\n"
        elif kid == "0":
            _commit(); text += " "
        else:
            if p_key == kid:
                p_idx += 1; p_time = now
            else:
                _commit()
                p_key = kid; p_idx = 0; p_time = now
        _refresh()
        return None

    def _on_timeout(now):
        if p_key and (now - p_time) >= _T9_TIMEOUT:
            _commit(); _refresh()

    def _on_swipe():
        _commit()
        if text:
            slbl.text = "SAVING..."
            slbl.color = ui.C_AMBER
            ok = _write(path, text)
            slbl.text  = "SAVED!" if ok else "SAVE ERR - USB WRITE BLOCKED"
            slbl.color = ui.C_GREEN_HI if ok else ui.C_RED
            saved[0] = ok
            time.sleep(1.0)
        return True

    _run_t9_loop(display, touch, keyboard, W, H, sc, key_areas,
                 _on_key, _on_timeout, _on_swipe)

    display.root_group = displayio.Group()
    del sc
    gc.collect()
    return saved[0]


# ── Entry point ───────────────────────────────────────────────────────────────

def run(display, touch, keyboard, W, H):
    _ensure_dir()
    while True:
        res = _list_screen(display, touch, W, H)
        if res[0] == "quit":
            break
        elif res[0] == "new":
            # Step 1: get a name
            raw_name = _name_screen(display, touch, keyboard, W, H)
            stem = _sanitize(raw_name) if raw_name else None
            if stem:
                fname = _unique_name(stem, _list_notes())
            else:
                fname = _next_auto_name(_list_notes())
            _editor(display, touch, keyboard, W, H, _DATA_DIR + "/" + fname)
        elif res[0] == "edit":
            _editor(display, touch, keyboard, W, H, res[1])
    display.root_group = displayio.Group()
