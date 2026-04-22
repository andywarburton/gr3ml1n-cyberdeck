# apps/snake/app.py
# CyberDeck app: Snake | portrait 240×320
#
# Classic Nokia-style snake rendered as ASCII art.
# Arrow keys to move, swipe up to quit, ENTER to restart after game over.
# The snake grows every time it eats food (*). Hitting a wall or itself ends the game.

import displayio
import terminalio
import time
import random
import gc
from adafruit_display_text import label
from waveshare_touch import classify_gesture
import cyber_ui as ui

# ── Grid constants ─────────────────────────────────────────────────────────────
COLS = 20   # 20 × 12px = 240px at scale=2 (exact screen width)
ROWS = 17   # 17 × 16px = 272px at scale=2 (fits in 279px content area)

INNER_R_MIN = 1
INNER_R_MAX = ROWS - 2   # 15
INNER_C_MIN = 1
INNER_C_MAX = COLS - 2   # 18

# ── Helper functions ───────────────────────────────────────────────────────────

def _make_grid():
    grid = []
    for r in range(ROWS):
        if r == 0 or r == ROWS - 1:
            row = ['+'] + ['-'] * (COLS - 2) + ['+']
        else:
            row = ['|'] + [' '] * (COLS - 2) + ['|']
        grid.append(row)
    return grid


def _render(grid):
    parts = []
    for row in grid:
        parts.append(''.join(row))
    return '\n'.join(parts)


def _place_food(grid, snake):
    snake_set = set(snake)
    free = []
    for r in range(INNER_R_MIN, INNER_R_MAX + 1):
        for c in range(INNER_C_MIN, INNER_C_MAX + 1):
            if grid[r][c] == ' ':
                free.append((r, c))
    if not free:
        return None
    return free[random.randint(0, len(free) - 1)]


def _center18(text):
    text = text[:18]
    pad = 18 - len(text)
    return ' ' * (pad // 2) + text + ' ' * (pad - pad // 2)


def _draw_gameover(grid, score):
    lines = [
        '',
        '** GAME OVER **',
        '',
        'SCORE: {}'.format(score),
        '',
        'ENTER=NEW GAME',
        '',
    ]
    for i, line in enumerate(lines):
        r = 5 + i
        inner = list(_center18(line))
        for c in range(18):
            grid[r][INNER_C_MIN + c] = inner[c]


def _new_game():
    grid = _make_grid()
    # Initial snake: 3 cells moving right, centred on the grid
    # snake[0]=tail, snake[-1]=head
    snake = [(8, 8), (8, 9), (8, 10)]
    grid[8][8]  = 'o'
    grid[8][9]  = 'o'
    grid[8][10] = 'O'
    direction   = (0, 1)   # right
    next_dir    = (0, 1)
    food        = _place_food(grid, snake)
    grid[food[0]][food[1]] = '.'
    score         = 0
    grow_pending  = 0
    frame_counter = 0
    move_interval = 4
    return (grid, snake, direction, next_dir, food,
            score, grow_pending, frame_counter, move_interval)


# ── App entry point ────────────────────────────────────────────────────────────

def run(display, touch, keyboard, W, H):
    (grid, snake, direction, next_dir, food,
     score, grow_pending, frame_counter, move_interval) = _new_game()

    state = "playing"

    # Build scene once — only label text changes during play
    scene = displayio.Group()
    title_lbl, score_lbl = ui.make_title_bar(scene, "SNAKE", "SCORE:0")
    ui.make_scan_bg(scene, ui.CONTENT_Y, ui.CONTENT_H)

    game_lbl = label.Label(terminalio.FONT, text=_render(grid),
                           color=ui.C_GREEN_HI, scale=2)
    game_lbl.anchor_point = (0.0, 0.0)
    game_lbl.anchored_position = (0, ui.CONTENT_Y + 3)
    scene.append(game_lbl)

    ui.make_footer(scene, "ARROWS=MOVE  SWIPE UP=QUIT")
    display.root_group = scene

    finger_down = False
    sx = sy = lx = ly = 0

    while True:

        # ── Keyboard ──────────────────────────────────────────────────────────
        if keyboard:
            kbd = keyboard.poll()

            if state == "playing":
                if kbd['escape']:
                    break
                if kbd['up']    and direction != (1, 0):  next_dir = (-1, 0)
                elif kbd['down']  and direction != (-1, 0): next_dir = (1, 0)
                elif kbd['left']  and direction != (0, 1):  next_dir = (0, -1)
                elif kbd['right'] and direction != (0, -1): next_dir = (0, 1)

            elif state == "gameover":
                if kbd['escape']:
                    break
                if kbd['enter']:
                    (grid, snake, direction, next_dir, food,
                     score, grow_pending, frame_counter, move_interval) = _new_game()
                    score_lbl.text = "SCORE:0"
                    game_lbl.text  = _render(grid)
                    state = "playing"

        # ── Touch ─────────────────────────────────────────────────────────────
        x, y, touching = touch.read()

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
            if action and action[0] == "SWIPE UP":
                break

        # ── Game tick ─────────────────────────────────────────────────────────
        if state == "playing" and frame_counter % move_interval == 0:
            direction = next_dir

            head_r, head_c = snake[-1]
            new_r = head_r + direction[0]
            new_c = head_c + direction[1]

            # Collision: wall
            hit_wall = (new_r < INNER_R_MIN or new_r > INNER_R_MAX or
                        new_c < INNER_C_MIN or new_c > INNER_C_MAX)

            # Collision: self (check before appending new head)
            hit_self = (new_r, new_c) in snake

            if hit_wall or hit_self:
                state = "gameover"
                _draw_gameover(grid, score)
                game_lbl.text = _render(grid)

            else:
                # Move: add new head
                snake.append((new_r, new_c))

                # Remove tail unless growing
                if grow_pending > 0:
                    grow_pending -= 1
                else:
                    tail_r, tail_c = snake.pop(0)
                    grid[tail_r][tail_c] = '.'

                # Update grid chars
                grid[head_r][head_c] = 'o'   # old head becomes body
                grid[new_r][new_c]   = 'O'   # new head

                # Food collection
                if (new_r, new_c) == food:
                    score        += 1
                    grow_pending += 1
                    move_interval = max(2, 6 - score // 5)
                    score_lbl.text = "SCORE:{}".format(score)

                    new_food = _place_food(grid, snake)
                    if new_food is None:
                        # Board is full — perfect game
                        state = "gameover"
                        _draw_gameover(grid, score)
                    else:
                        food = new_food
                        grid[food[0]][food[1]] = '.'

                game_lbl.text = _render(grid)

        time.sleep(0.04)
        frame_counter += 1

    display.root_group = displayio.Group()
    gc.collect()
