# apps/themes/app.py
# CyberDeck app: Theme Selector | portrait 240×320
#
# Supports pagination (5 themes per page).
# Touch: swipe left/right to page, tap to apply. Swipe up to quit.
# Keyboard: up/down to navigate (auto-pages), enter to apply, esc to quit.

import displayio
import terminalio
import time
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

# ── Layout ─────────────────────────────────────────────────────────────────────
_BTN_H   = 46
_BTN_GAP = 4
_BTN_X   = 2
_BTN_W   = ui.W - 4   # 236
_IND_W   = 4

_SW_W     = 15
_SW_H     = 14
_SW_GAP   = 3
_SW_COUNT = 4
_SW_TOTAL = _SW_COUNT * _SW_W + (_SW_COUNT - 1) * _SW_GAP   # 69px
_SW_X0    = ui.W - _BTN_X - _SW_TOTAL - 4

_STATUS_H     = 22   # status label + separator line
_BTN_AREA_Y   = ui.CONTENT_Y + _STATUS_H
_BTN_AREA_H   = ui.CONTENT_H - _STATUS_H

THEMES_PER_PAGE = 5
_STACK_H = THEMES_PER_PAGE * _BTN_H + (THEMES_PER_PAGE - 1) * _BTN_GAP
_BTN_Y0  = _BTN_AREA_Y + (_BTN_AREA_H - _STACK_H) // 2


def _total_pages():
    n = len(ui.THEME_NAMES)
    return (n + THEMES_PER_PAGE - 1) // THEMES_PER_PAGE


def _page_for(idx):
    return idx // THEMES_PER_PAGE


def _themes_on_page(page):
    start = page * THEMES_PER_PAGE
    return ui.THEME_NAMES[start:start + THEMES_PER_PAGE]


def _build_scene(display, W, active, cursor_global, page):
    total_pages = _total_pages()
    themes_on_page = _themes_on_page(page)
    cursor_local = cursor_global - page * THEMES_PER_PAGE

    scene = displayio.Group()
    ui.make_title_bar(scene, "SYS:THEMES",
                      "{}/{}".format(page + 1, total_pages))
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    # Status label
    status_lbl = label.Label(terminalio.FONT,
        text="ACTIVE: " + active.upper(),
        color=ui.C_GREEN_HI, scale=1)
    status_lbl.anchor_point = (0.5, 0.5)
    status_lbl.anchored_position = (W // 2, ui.CONTENT_Y + 11)
    scene.append(status_lbl)

    ui.solid_rect(scene, 4, ui.CONTENT_Y + _STATUS_H - 1, W - 8, 1, ui.C_GREEN_DIM)

    # Theme buttons
    btn_info = []
    for i, name in enumerate(themes_on_page):
        t  = ui.THEMES[name]
        by = _BTN_Y0 + i * (_BTN_H + _BTN_GAP)
        is_active = (name == active)
        is_cursor = (i == cursor_local)

        ui.solid_rect(scene, _BTN_X, by, _BTN_W, _BTN_H, t["bg_header"])

        if is_active:
            ind_col = t["glow"]
        elif is_cursor:
            ind_col = t["mid"]
        else:
            ind_col = t["bg_header"]
        ui.solid_rect(scene, _BTN_X, by, _IND_W, _BTN_H, ind_col)

        n_lbl = label.Label(terminalio.FONT,
            text=name.upper(), color=t["hi"], scale=2)
        n_lbl.anchor_point = (0.0, 0.5)
        n_lbl.anchored_position = (_BTN_X + _IND_W + 6, by + _BTN_H // 2)
        scene.append(n_lbl)

        swatch_colors = [t["bg_panel"], t["mid"], t["hi"], t["glow"]]
        for j, col in enumerate(swatch_colors):
            sx    = _SW_X0 + j * (_SW_W + _SW_GAP)
            sy_sw = by + (_BTN_H - _SW_H) // 2
            ui.solid_rect(scene, sx, sy_sw, _SW_W, _SW_H, col)

        if i < len(themes_on_page) - 1:
            ui.solid_rect(scene, _BTN_X + _IND_W + 2, by + _BTN_H,
                          _BTN_W - _IND_W - 2, 1, t["mid"])

        btn_info.append({"name": name, "y": by})

    # Page indicator dots
    if total_pages > 1:
        dot_spacing = 12
        dots_total_w = (total_pages - 1) * dot_spacing
        dot_base_x = W // 2 - dots_total_w // 2
        dot_y = ui.FOOTER_Y - 9
        for p in range(total_pages):
            col = ui.C_GREEN_HI if p == page else ui.C_GREEN_DIM
            ui.solid_rect(scene, dot_base_x + p * dot_spacing - 2, dot_y, 5, 5, col)

    ui.make_footer(scene, "^ BACK  ^v SEL  <> PG  ENT")
    display.root_group = scene
    return scene, status_lbl, btn_info


def run(display, touch, keyboard, W, H):
    active = ui.get_active_theme()
    total  = len(ui.THEME_NAMES)

    # Start on the page that contains the active theme
    cursor_global = ui.THEME_NAMES.index(active) if active in ui.THEME_NAMES else 0
    page          = _page_for(cursor_global)
    total_pages   = _total_pages()

    scene, status_lbl, btn_info = _build_scene(display, W, active, cursor_global, page)

    finger_down   = False
    sx = sy = lx = ly = 0
    needs_rebuild = False

    while True:
        if needs_rebuild:
            scene, status_lbl, btn_info = _build_scene(
                display, W, active, cursor_global, page)
            needs_rebuild = False

        if keyboard:
            kbd = keyboard.poll()
            if kbd['escape']:
                break
            if kbd['up']:
                cursor_global = (cursor_global - 1) % total
                new_page = _page_for(cursor_global)
                if new_page != page:
                    page = new_page
                needs_rebuild = True
            elif kbd['down']:
                cursor_global = (cursor_global + 1) % total
                new_page = _page_for(cursor_global)
                if new_page != page:
                    page = new_page
                needs_rebuild = True
            elif kbd['left']:
                if page > 0:
                    page -= 1
                    cursor_global = page * THEMES_PER_PAGE
                    needs_rebuild = True
            elif kbd['right']:
                if page < total_pages - 1:
                    page += 1
                    cursor_global = page * THEMES_PER_PAGE
                    needs_rebuild = True
            elif kbd['enter']:
                active = ui.THEME_NAMES[cursor_global]
                ui.set_theme(active)
                needs_rebuild = True

        x, y, touching = touch.read()
        time.sleep(0.04)

        if touching:
            lx, ly = x, y
            if not finger_down:
                finger_down = True
                sx, sy = x, y
        elif finger_down:
            finger_down = False

            action = classify_gesture(
                sx, sy, lx, ly, W, H,
                swipe_edge=ui.SWIPE_EDGE, swipe_min_dist=ui.SWIPE_MIN,
            )
            if action:
                gesture = action[0]
                if gesture == "SWIPE UP":
                    break
                elif gesture == "SWIPE LEFT" and page < total_pages - 1:
                    page += 1
                    cursor_global = page * THEMES_PER_PAGE
                    needs_rebuild = True
                elif gesture == "SWIPE RIGHT" and page > 0:
                    page -= 1
                    cursor_global = page * THEMES_PER_PAGE
                    needs_rebuild = True
            else:
                # Tap — find which button was hit
                for btn in btn_info:
                    if btn["y"] <= sy <= btn["y"] + _BTN_H:
                        active = btn["name"]
                        ui.set_theme(active)
                        cursor_global = ui.THEME_NAMES.index(active)
                        needs_rebuild = True
                        break

    display.root_group = displayio.Group()
