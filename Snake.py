"""
Advanced Snake
==============

A single-file, zero-dependency Snake game built on tkinter.

Features
--------
* Smooth interpolated movement (logic ticks decoupled from a 60 FPS render loop)
* Five game modes: Classic, Wrap, Maze, Frenzy, Duel (vs. a BFS-pathfinding rival snake)
* Six power-ups: Gold, Slow-Mo, Ghost, Shrink, Magnet, Double Points
* Combo multiplier chain, level progression, escalating speed
* Particle effects, screen shake, hit flash, pulsing food, gradient snake body
* Per-mode persistent high-score tables (JSON next to this file)
* Input buffering so fast double-turns are never dropped
* Optional beeps on Windows (winsound), silently disabled elsewhere

Run
---
    python snake.py

Controls
--------
    Arrows / WASD  move            P or Space  pause
    Enter          select          M           mute
    R              restart         Esc         back / quit
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import tkinter as tk
from tkinter import font as tkfont

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

COLS, ROWS = 30, 22
CELL = 26
HUD_H = 78

BOARD_W = COLS * CELL
BOARD_H = ROWS * CELL
WIN_W = BOARD_W
WIN_H = BOARD_H + HUD_H

FRAME_MS = 16                      # ~60 FPS render loop
BASE_STEP = 0.135                  # seconds per logic tick at level 1
MIN_STEP = 0.045                   # speed ceiling
FOODS_PER_LEVEL = 5
COMBO_WINDOW = 3.6                 # seconds to chain a combo
MAX_COMBO = 9
POWERUP_LIFETIME = 9.0
MAX_SCORES_PER_MODE = 5

SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "snake_highscores.json")

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)

KEY_DIRS = {
    "up": UP, "w": UP, "k": UP,
    "down": DOWN, "s": DOWN, "j": DOWN,
    "left": LEFT, "a": LEFT, "h": LEFT,
    "right": RIGHT, "d": RIGHT, "l": RIGHT,
}


class T:
    """Theme."""
    bg = "#080b14"
    board = "#0d1220"
    board_alt = "#0f1526"
    grid = "#161e33"
    wall = "#243055"
    wall_lit = "#37477a"
    text = "#e8eeff"
    muted = "#6f7da3"
    dim = "#414d70"
    accent = "#5ad1ff"
    accent2 = "#a78bfa"
    good = "#4ade80"
    bad = "#ff4d6d"
    gold = "#ffd23f"
    panel = "#111829"
    panel_edge = "#26314f"

    snake_head = "#a7ffcd"
    snake_tail = "#0f8a53"
    rival_head = "#ffc9a7"
    rival_tail = "#a34a12"


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def hex_to_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % (int(clamp(r, 0, 255)),
                              int(clamp(g, 0, 255)),
                              int(clamp(b, 0, 255)))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1: str, c2: str, t: float) -> str:
    t = clamp(t, 0.0, 1.0)
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex(lerp(r1, r2, t), lerp(g1, g2, t), lerp(b1, b2, t))


def shade(color: str, amount: float) -> str:
    """amount > 0 lightens toward white, < 0 darkens toward black."""
    return lerp_color(color, "#ffffff" if amount > 0 else "#000000", abs(amount))


def neighbours(cell: tuple[int, int], wrap: bool) -> Iterable[tuple[int, int]]:
    x, y = cell
    for dx, dy in (UP, DOWN, LEFT, RIGHT):
        nx, ny = x + dx, y + dy
        if wrap:
            yield nx % COLS, ny % ROWS
        elif 0 <= nx < COLS and 0 <= ny < ROWS:
            yield nx, ny


# --------------------------------------------------------------------------- #
# Pathfinding (used by the rival snake in Duel mode)
# --------------------------------------------------------------------------- #

def bfs_step(start: tuple[int, int],
             goals: set[tuple[int, int]],
             blocked: set[tuple[int, int]],
             wrap: bool) -> tuple[int, int] | None:
    """First cell along a shortest path from `start` to any goal, or None."""
    if not goals:
        return None
    frontier = deque()
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    for n in neighbours(start, wrap):
        if n in blocked and n not in goals:
            continue
        came_from[n] = start
        if n in goals:
            return n
        frontier.append(n)

    while frontier:
        cur = frontier.popleft()
        for n in neighbours(cur, wrap):
            if n in came_from:
                continue
            if n in blocked and n not in goals:
                continue
            came_from[n] = cur
            if n in goals:
                node = n
                while came_from[node] != start:
                    node = came_from[node]
                return node
            frontier.append(n)
    return None


def open_space(start: tuple[int, int],
               blocked: set[tuple[int, int]],
               wrap: bool,
               limit: int = 220) -> int:
    """Flood-fill size of the region reachable from `start` (capped)."""
    if start in blocked:
        return 0
    seen = {start}
    stack = [start]
    while stack and len(seen) < limit:
        cur = stack.pop()
        for n in neighbours(cur, wrap):
            if n not in seen and n not in blocked:
                seen.add(n)
                stack.append(n)
    return len(seen)


# --------------------------------------------------------------------------- #
# Sound
# --------------------------------------------------------------------------- #

class Sound:
    """Non-blocking beeps via winsound on Windows; a no-op everywhere else."""

    TONES = {
        "eat":    [(880, 28), (1180, 34)],
        "gold":   [(1046, 26), (1318, 26), (1568, 40)],
        "power":  [(660, 26), (990, 32)],
        "level":  [(784, 40), (988, 40), (1175, 60)],
        "die":    [(420, 90), (300, 110), (200, 150)],
        "select": [(620, 18)],
        "kill":   [(1300, 26), (900, 30), (1500, 40)],
    }

    def __init__(self) -> None:
        self.enabled = False
        self.muted = False
        self._beep = None
        if sys.platform == "win32":
            try:
                import winsound
                self._beep = winsound.Beep
                self.enabled = True
            except Exception:
                self.enabled = False

    def play(self, name: str) -> None:
        if not self.enabled or self.muted:
            return
        tones = self.TONES.get(name)
        if not tones:
            return
        import threading

        def run():
            try:
                for freq, ms in tones:
                    self._beep(freq, ms)
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()


# --------------------------------------------------------------------------- #
# Particles
# --------------------------------------------------------------------------- #

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: str


class Particles:
    def __init__(self) -> None:
        self.items: list[Particle] = []

    def burst(self, x: float, y: float, color: str, count: int = 16,
              speed: float = 150.0, size: float = 4.0, life: float = 0.5) -> None:
        for _ in range(count):
            ang = random.uniform(0, math.tau)
            mag = random.uniform(0.25, 1.0) * speed
            ln = life * random.uniform(0.6, 1.3)
            self.items.append(Particle(
                x, y,
                math.cos(ang) * mag, math.sin(ang) * mag,
                ln, ln,
                size * random.uniform(0.55, 1.35),
                color,
            ))

    def ring(self, x: float, y: float, color: str, count: int = 18,
             speed: float = 190.0) -> None:
        for i in range(count):
            ang = math.tau * i / count
            self.items.append(Particle(
                x, y,
                math.cos(ang) * speed, math.sin(ang) * speed,
                0.42, 0.42, 3.0, color,
            ))

    def update(self, dt: float) -> None:
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 210 * dt          # gentle gravity
            p.vx *= 0.94
            p.vy *= 0.94
            alive.append(p)
        self.items = alive

    def clear(self) -> None:
        self.items.clear()


# --------------------------------------------------------------------------- #
# Modes & power-ups
# --------------------------------------------------------------------------- #

class Mode(Enum):
    CLASSIC = "Classic"
    WRAP = "Endless"
    MAZE = "Maze"
    FRENZY = "Frenzy"
    DUEL = "Duel"

    @property
    def blurb(self) -> str:
        return {
            Mode.CLASSIC: "Walls are lethal. The honest original.",
            Mode.WRAP:    "Edges wrap around. Only you can kill you.",
            Mode.MAZE:    "Walls spawn and multiply every level.",
            Mode.FRENZY:  "Fast start, two apples, power-ups everywhere.",
            Mode.DUEL:    "A rival snake hunts the same apples. Cut it off.",
        }[self]

    @property
    def wrap(self) -> bool:
        return self is Mode.WRAP

    @property
    def foods(self) -> int:
        return 2 if self is Mode.FRENZY else 1

    @property
    def base_step(self) -> float:
        return 0.105 if self is Mode.FRENZY else BASE_STEP

    @property
    def powerup_gap(self) -> tuple[float, float]:
        return (4.0, 8.0) if self is Mode.FRENZY else (8.0, 15.0)

    @property
    def obstacles(self) -> bool:
        return self in (Mode.MAZE, Mode.DUEL)


class Power(Enum):
    GOLD = "Gold"
    SLOW = "Slow-Mo"
    GHOST = "Ghost"
    SHRINK = "Shrink"
    MAGNET = "Magnet"
    DOUBLE = "2x Points"

    @property
    def color(self) -> str:
        return {
            Power.GOLD: T.gold,
            Power.SLOW: "#7dd3fc",
            Power.GHOST: "#c4b5fd",
            Power.SHRINK: "#fca5a5",
            Power.MAGNET: "#f472b6",
            Power.DOUBLE: "#86efac",
        }[self]

    @property
    def glyph(self) -> str:
        return {
            Power.GOLD: "$", Power.SLOW: "T", Power.GHOST: "G",
            Power.SHRINK: "-", Power.MAGNET: "M", Power.DOUBLE: "2",
        }[self]

    @property
    def duration(self) -> float:
        return {
            Power.SLOW: 6.0, Power.GHOST: 6.5, Power.MAGNET: 6.0,
            Power.DOUBLE: 10.0,
        }.get(self, 0.0)

    @property
    def instant(self) -> bool:
        return self.duration == 0.0


POWER_WEIGHTS = {
    Power.GOLD: 26, Power.SLOW: 15, Power.GHOST: 14,
    Power.SHRINK: 13, Power.MAGNET: 14, Power.DOUBLE: 18,
}


@dataclass
class Pickup:
    cell: tuple[int, int]
    kind: Power
    ttl: float = POWERUP_LIFETIME


class State(Enum):
    MENU = "menu"
    HELP = "help"
    PLAYING = "playing"
    PAUSED = "paused"
    DEAD = "dead"


# --------------------------------------------------------------------------- #
# Snakes
# --------------------------------------------------------------------------- #

class Snake:
    def __init__(self, cells: list[tuple[int, int]], direction: tuple[int, int],
                 head_color: str, tail_color: str) -> None:
        self.body: deque[tuple[int, int]] = deque(cells)
        self.prev_body: list[tuple[int, int]] = list(cells)
        self.direction = direction
        self.pending: deque[tuple[int, int]] = deque()
        self.grow = 0
        self.alive = True
        self.head_color = head_color
        self.tail_color = tail_color

    @property
    def head(self) -> tuple[int, int]:
        return self.body[0]

    @property
    def tail(self) -> tuple[int, int]:
        return self.body[-1]

    def __len__(self) -> int:
        return len(self.body)

    def cells(self) -> set[tuple[int, int]]:
        return set(self.body)

    def turn(self, d: tuple[int, int]) -> None:
        """Buffer a direction change; up to 3 queued so fast turns survive."""
        ref = self.pending[-1] if self.pending else self.direction
        if d == ref or (d[0] == -ref[0] and d[1] == -ref[1]):
            return
        if len(self.pending) < 3:
            self.pending.append(d)

    def next_head(self, wrap: bool,
                  direction: tuple[int, int] | None = None
                  ) -> tuple[int, int] | None:
        d = direction if direction is not None else (
            self.pending[0] if self.pending else self.direction)
        x, y = self.head
        nx, ny = x + d[0], y + d[1]
        if wrap:
            return nx % COLS, ny % ROWS
        if 0 <= nx < COLS and 0 <= ny < ROWS:
            return nx, ny
        return None

    def advance(self, wrap: bool) -> tuple[int, int] | None:
        """Move one cell. Returns the new head, or None if it hit a wall."""
        self.prev_body = list(self.body)
        if self.pending:
            self.direction = self.pending.popleft()
        nxt = self.next_head(wrap, self.direction)
        if nxt is None:
            return None
        self.body.appendleft(nxt)
        if self.grow > 0:
            self.grow -= 1
        else:
            self.body.pop()
        return nxt

    def shrink(self, fraction: float = 0.3, keep_min: int = 3) -> int:
        drop = int(len(self.body) * fraction)
        drop = min(drop, max(0, len(self.body) - keep_min))
        for _ in range(drop):
            self.body.pop()
        if len(self.prev_body) > len(self.body):
            self.prev_body = self.prev_body[:len(self.body)]
        return drop


class Rival(Snake):
    """A snake that seeks apples with BFS and avoids trapping itself."""

    def __init__(self, cells, direction) -> None:
        super().__init__(cells, direction, T.rival_head, T.rival_tail)
        self.respawn_in = 0.0

    def think(self, foods: set[tuple[int, int]],
              blocked: set[tuple[int, int]], wrap: bool) -> None:
        own = set(self.body)
        hard = (blocked | own) - {self.tail}
        target = bfs_step(self.head, foods, hard, wrap)

        if target is None:
            # No route to food: take the neighbour with the most breathing room.
            best, best_score = None, -1
            for n in neighbours(self.head, wrap):
                if n in hard:
                    continue
                score = open_space(n, hard, wrap)
                if score > best_score:
                    best, best_score = n, score
            target = best

        if target is None:
            return                                   # trapped; keep course
        hx, hy = self.head
        dx, dy = target[0] - hx, target[1] - hy
        if wrap:                                     # normalise wrap-around step
            if dx > 1:
                dx = -1
            elif dx < -1:
                dx = 1
            if dy > 1:
                dy = -1
            elif dy < -1:
                dy = 1
        if (dx, dy) in (UP, DOWN, LEFT, RIGHT):
            self.pending.clear()
            self.pending.append((dx, dy))


# --------------------------------------------------------------------------- #
# High scores
# --------------------------------------------------------------------------- #

def load_scores() -> dict[str, list[int]]:
    try:
        with open(SCORE_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        out: dict[str, list[int]] = {}
        for mode in Mode:
            vals = raw.get(mode.value, [])
            if isinstance(vals, list):
                out[mode.value] = sorted(
                    (int(v) for v in vals if isinstance(v, (int, float))),
                    reverse=True)[:MAX_SCORES_PER_MODE]
            else:
                out[mode.value] = []
        return out
    except Exception:
        return {m.value: [] for m in Mode}


def save_scores(scores: dict[str, list[int]]) -> None:
    try:
        with open(SCORE_FILE, "w", encoding="utf-8") as fh:
            json.dump(scores, fh, indent=2)
    except Exception:
        pass          # a read-only disk should never crash the game


# --------------------------------------------------------------------------- #
# Game
# --------------------------------------------------------------------------- #

class Game:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Advanced Snake")
        root.resizable(False, False)
        root.configure(bg=T.bg)

        self.canvas = tk.Canvas(root, width=WIN_W, height=WIN_H,
                                bg=T.bg, highlightthickness=0, bd=0)
        self.canvas.pack()

        self.f_title = self._font(46, "bold")
        self.f_big = self._font(30, "bold")
        self.f_mid = self._font(17, "bold")
        self.f_body = self._font(13)
        self.f_small = self._font(11)
        self.f_tiny = self._font(9, "bold")
        self.f_hud = self._font(20, "bold")
        self.f_label = self._font(9, "bold")

        self.sound = Sound()
        self.particles = Particles()
        self.scores = load_scores()

        self.state = State.MENU
        self.menu_index = 0
        self.mode = Mode.CLASSIC
        self.clock = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.flash_color = T.bad
        self.new_record = False
        self.death_reason = ""
        self.ox = self.oy = 0.0

        self.snake: Snake | None = None
        self.rival: Rival | None = None
        self.obstacles: set[tuple[int, int]] = set()
        self.foods: set[tuple[int, int]] = set()
        self.pickups: list[Pickup] = []
        self.effects: dict[Power, float] = {}
        self.score = 0
        self.level = 1
        self.eaten = 0
        self.combo = 0
        self.combo_timer = 0.0
        self.kills = 0
        self.elapsed = 0.0
        self.acc = 0.0
        self.step_time = BASE_STEP
        self.powerup_timer = 0.0
        self.food_pop: dict[tuple[int, int], float] = {}

        root.bind("<KeyPress>", self.on_key)
        self.last_time = time.perf_counter()
        self.root.after(FRAME_MS, self.tick)

    # -- infrastructure ---------------------------------------------------- #

    def _font(self, size: int, weight: str = "normal"):
        for family in ("Segoe UI", "Helvetica Neue", "DejaVu Sans", "Helvetica"):
            try:
                return tkfont.Font(family=family, size=size, weight=weight)
            except Exception:
                continue
        return tkfont.Font(size=size, weight=weight)

    # -- input ------------------------------------------------------------- #

    def on_key(self, event: tk.Event) -> None:
        key = (event.keysym or "").lower()

        if key == "m":
            self.sound.muted = not self.sound.muted
            return

        if self.state is State.MENU:
            if key in ("up", "w"):
                self.menu_index = (self.menu_index - 1) % len(Mode)
                self.sound.play("select")
            elif key in ("down", "s"):
                self.menu_index = (self.menu_index + 1) % len(Mode)
                self.sound.play("select")
            elif key in ("return", "kp_enter", "space"):
                self.start(list(Mode)[self.menu_index])
            elif key in ("h", "slash", "question"):
                self.state = State.HELP
            elif key == "escape":
                self.root.destroy()
            return

        if self.state is State.HELP:
            if key in ("escape", "return", "kp_enter", "space", "h"):
                self.state = State.MENU
            return

        if self.state is State.DEAD:
            if key in ("r", "return", "kp_enter", "space"):
                self.start(self.mode)
            elif key == "escape":
                self.state = State.MENU
            return

        if self.state is State.PAUSED:
            if key in ("p", "space", "return", "kp_enter"):
                self.state = State.PLAYING
                self.last_time = time.perf_counter()
            elif key == "escape":
                self.state = State.MENU
            elif key == "r":
                self.start(self.mode)
            return

        # PLAYING
        if key in ("p", "space"):
            self.state = State.PAUSED
        elif key == "escape":
            self.state = State.PAUSED
        elif key == "r":
            self.start(self.mode)
        elif key in KEY_DIRS and self.snake is not None:
            self.snake.turn(KEY_DIRS[key])

    # -- setup ------------------------------------------------------------- #

    def start(self, mode: Mode) -> None:
        self.mode = mode
        self.state = State.PLAYING
        self.score = 0
        self.level = 1
        self.eaten = 0
        self.combo = 0
        self.combo_timer = 0.0
        self.kills = 0
        self.elapsed = 0.0
        self.acc = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.new_record = False
        self.death_reason = ""
        self.effects.clear()
        self.pickups.clear()
        self.foods.clear()
        self.food_pop.clear()
        self.particles.clear()
        self.obstacles.clear()

        cy = ROWS // 2
        start_cells = [(6, cy), (5, cy), (4, cy)]
        self.snake = Snake(start_cells, RIGHT, T.snake_head, T.snake_tail)

        self.rival = None
        if mode is Mode.DUEL:
            self.rival = Rival([(COLS - 7, cy), (COLS - 6, cy), (COLS - 5, cy)],
                               LEFT)

        if mode.obstacles:
            self.build_obstacles(4 if mode is Mode.MAZE else 3)

        for _ in range(mode.foods):
            self.spawn_food()

        lo, hi = mode.powerup_gap
        self.powerup_timer = random.uniform(lo, hi)
        self.step_time = mode.base_step
        self.last_time = time.perf_counter()
        self.sound.play("select")

    def occupied(self, include_food: bool = True) -> set[tuple[int, int]]:
        out = set(self.obstacles)
        if self.snake:
            out |= self.snake.cells()
        if self.rival:
            out |= self.rival.cells()
        if include_food:
            out |= self.foods
            out |= {p.cell for p in self.pickups}
        return out

    def free_cells(self) -> list[tuple[int, int]]:
        taken = self.occupied()
        return [(x, y) for x in range(COLS) for y in range(ROWS)
                if (x, y) not in taken]

    def build_obstacles(self, count: int) -> None:
        """Add short wall segments, keeping the board connected and fair."""
        # Never drop a wall on the spawn corridors, on a live snake, on the
        # cells just ahead of the player, or on anything collectable.
        avoid = {(x, y)
                 for x in range(2, 9)
                 for y in range(ROWS // 2 - 2, ROWS // 2 + 3)}
        if self.rival:
            avoid |= {(x, y)
                      for x in range(COLS - 9, COLS - 1)
                      for y in range(ROWS // 2 - 2, ROWS // 2 + 3)}
            avoid |= self.rival.cells()
        avoid |= self.foods
        avoid |= {p.cell for p in self.pickups}

        if self.snake is not None:
            avoid |= self.snake.cells()
            hx, hy = self.snake.head
            dx, dy = self.snake.direction
            for i in range(1, 6):                 # clear line of sight ahead
                cx, cy = hx + dx * i, hy + dy * i
                if self.mode.wrap:
                    cx, cy = cx % COLS, cy % ROWS
                avoid.add((cx, cy))

        placed = 0
        for _ in range(count * 60):
            if placed >= count:
                break
            length = random.randint(2, 5)
            horizontal = random.random() < 0.5
            x = random.randint(1, COLS - (length + 1 if horizontal else 2))
            y = random.randint(1, ROWS - (2 if horizontal else length + 1))
            seg = {(x + i, y) if horizontal else (x, y + i)
                   for i in range(length)}

            if seg & avoid or seg & self.obstacles:
                continue
            # keep a one-cell gap around existing walls so corridors stay open
            halo = set()
            for cx, cy in seg:
                for ddx in (-1, 0, 1):
                    for ddy in (-1, 0, 1):
                        halo.add((cx + ddx, cy + ddy))
            if halo & self.obstacles:
                continue

            candidate = self.obstacles | seg
            start = self.snake.head if self.snake is not None else (5, ROWS // 2)
            reachable = COLS * ROWS - len(candidate)
            if open_space(start, candidate, self.mode.wrap,
                          limit=reachable) < reachable:
                continue                          # would cut the board in two

            self.obstacles = candidate
            placed += 1

    def spawn_food(self) -> None:
        cells = self.free_cells()
        if not cells:
            return
        # bias slightly away from the head so food is not free
        head = self.snake.head if self.snake else (COLS // 2, ROWS // 2)
        best = max(random.sample(cells, min(len(cells), 8)),
                   key=lambda c: abs(c[0] - head[0]) + abs(c[1] - head[1]))
        self.foods.add(best)
        self.food_pop[best] = 0.0

    def spawn_pickup(self) -> None:
        cells = self.free_cells()
        if not cells:
            return
        kinds = list(POWER_WEIGHTS)
        kind = random.choices(kinds, weights=[POWER_WEIGHTS[k] for k in kinds])[0]
        self.pickups.append(Pickup(random.choice(cells), kind))

    # -- main loop --------------------------------------------------------- #

    def tick(self) -> None:
        now = time.perf_counter()
        dt = min(now - self.last_time, 0.10)     # clamp after window drags
        self.last_time = now
        self.clock += dt
        try:
            self.update(dt)
            self.render()
        finally:
            self.root.after(FRAME_MS, self.tick)

    def update(self, dt: float) -> None:
        self.particles.update(dt)

        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 42)
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt * 2.2)

        if self.shake > 0.2:
            self.ox = random.uniform(-self.shake, self.shake)
            self.oy = random.uniform(-self.shake, self.shake)
        else:
            self.ox = self.oy = 0.0

        if self.state is not State.PLAYING or self.snake is None:
            return

        self.elapsed += dt

        for cell in list(self.food_pop):
            self.food_pop[cell] += dt

        if self.combo_timer > 0:
            self.combo_timer = max(0.0, self.combo_timer - dt)
            if self.combo_timer == 0.0:
                self.combo = 0

        for power in list(self.effects):
            self.effects[power] -= dt
            if self.effects[power] <= 0:
                del self.effects[power]

        for pickup in list(self.pickups):
            pickup.ttl -= dt
            if pickup.ttl <= 0:
                self.pickups.remove(pickup)

        self.powerup_timer -= dt
        if self.powerup_timer <= 0:
            lo, hi = self.mode.powerup_gap
            self.powerup_timer = random.uniform(lo, hi)
            if len(self.pickups) < 2:
                self.spawn_pickup()

        if self.rival and not self.rival.alive:
            self.rival.respawn_in -= dt
            if self.rival.respawn_in <= 0:
                self.respawn_rival()

        # fixed-timestep logic, interpolated rendering
        base = max(MIN_STEP, self.mode.base_step * (0.94 ** (self.level - 1)))
        if Power.SLOW in self.effects:
            base *= 1.75
        self.step_time = base

        self.acc += dt
        guard = 0
        while self.acc >= self.step_time and self.state is State.PLAYING:
            self.acc -= self.step_time
            self.logic_step()
            guard += 1
            if guard > 4:                       # never let a hitch cascade
                self.acc = 0.0
                break

    # -- one logic tick ---------------------------------------------------- #

    def logic_step(self) -> None:
        snake = self.snake
        if snake is None:
            return
        wrap = self.mode.wrap
        ghost = Power.GHOST in self.effects

        # magnet: drag every apple one cell toward the head
        if Power.MAGNET in self.effects and self.foods:
            hx, hy = snake.head
            moved: set[tuple[int, int]] = set()
            blocked = self.obstacles | snake.cells()
            for cell in sorted(self.foods):
                fx, fy = cell
                dx, dy = hx - fx, hy - fy
                step = (int(math.copysign(1, dx)), 0) if abs(dx) >= abs(dy) \
                    else (0, int(math.copysign(1, dy)))
                nx, ny = fx + step[0], fy + step[1]
                if wrap:
                    nx, ny = nx % COLS, ny % ROWS
                target = (nx, ny)
                if (dx == 0 and dy == 0) or not (0 <= nx < COLS) \
                        or not (0 <= ny < ROWS) or target in blocked \
                        or target in moved:
                    moved.add(cell)
                    continue
                moved.add(target)
                if cell in self.food_pop:
                    self.food_pop[target] = self.food_pop.pop(cell)
            self.foods = moved

        # rival decides before anyone moves
        if self.rival and self.rival.alive:
            blocked = self.obstacles | snake.cells()
            self.rival.think(self.foods, blocked, wrap)

        new_head = snake.advance(wrap)
        if new_head is None:
            self.die("You drove into the wall")
            return

        rival_head = None
        if self.rival and self.rival.alive:
            rival_head = self.rival.advance(wrap)
            if rival_head is None:
                self.kill_rival("wall")
                rival_head = None

        # --- player collisions
        if not ghost:
            if new_head in list(snake.body)[1:]:
                self.die("You bit your own tail")
                return
            if new_head in self.obstacles:
                self.die("You drove into a wall block")
                return
            if self.rival and self.rival.alive:
                if new_head == self.rival.head:
                    self.kill_rival("headon")
                    self.die("Head-on with the rival")
                    return
                if new_head in self.rival.cells():
                    self.die("You ran into the rival")
                    return

        # --- rival collisions
        if self.rival and self.rival.alive and rival_head is not None:
            rival_body_rest = list(self.rival.body)[1:]
            if rival_head in rival_body_rest:
                self.kill_rival("self")
            elif rival_head in self.obstacles:
                self.kill_rival("wall")
            elif rival_head in set(list(snake.body)[1:]):
                self.kill_rival("player")
            elif rival_head in self.foods:
                self.foods.discard(rival_head)
                self.food_pop.pop(rival_head, None)
                self.rival.grow += 2
                self.particles.burst(*self.cell_center(rival_head),
                                     T.rival_head, count=10, speed=110)
                self.spawn_food()

        # --- pickups then food (a pickup under the apple still registers)
        for pickup in list(self.pickups):
            if pickup.cell == new_head:
                self.pickups.remove(pickup)
                self.apply_power(pickup.kind, new_head)

        if new_head in self.foods:
            self.eat(new_head)

    # -- events ------------------------------------------------------------ #

    def cell_center(self, cell: tuple[int, int]) -> tuple[float, float]:
        return ((cell[0] + 0.5) * CELL, HUD_H + (cell[1] + 0.5) * CELL)

    def eat(self, cell: tuple[int, int]) -> None:
        self.foods.discard(cell)
        self.food_pop.pop(cell, None)
        self.snake.grow += 2
        self.eaten += 1

        self.combo = min(self.combo + 1, MAX_COMBO) if self.combo_timer > 0 else 1
        self.combo_timer = COMBO_WINDOW

        points = (10 + 2 * (self.level - 1)) * self.combo
        if Power.DOUBLE in self.effects:
            points *= 2
        self.score += points

        cx, cy = self.cell_center(cell)
        self.particles.burst(cx, cy, T.bad, count=14, speed=145)
        if self.combo >= 3:
            self.particles.ring(cx, cy, T.gold, count=10, speed=120)
        self.sound.play("eat")
        self.spawn_food()

        if self.eaten % FOODS_PER_LEVEL == 0:
            self.level_up()

    def level_up(self) -> None:
        self.level += 1
        self.flash, self.flash_color = 0.55, T.accent
        self.sound.play("level")
        cx, cy = self.cell_center(self.snake.head)
        self.particles.ring(cx, cy, T.accent, count=22, speed=210)
        if self.mode is Mode.MAZE:
            self.build_obstacles(2)
        elif self.mode is Mode.DUEL and self.level % 2 == 0:
            self.build_obstacles(1)

    def apply_power(self, kind: Power, cell: tuple[int, int]) -> None:
        cx, cy = self.cell_center(cell)
        self.particles.ring(cx, cy, kind.color, count=18, speed=200)

        if kind is Power.GOLD:
            points = 50 * max(1, self.combo)
            if Power.DOUBLE in self.effects:
                points *= 2
            self.score += points
            self.flash, self.flash_color = 0.4, T.gold
            self.sound.play("gold")
        elif kind is Power.SHRINK:
            dropped = self.snake.shrink(0.3)
            self.score += dropped * 4
            self.sound.play("power")
        else:
            self.effects[kind] = max(self.effects.get(kind, 0.0), 0.0) \
                + kind.duration
            self.sound.play("power")

    def kill_rival(self, cause: str) -> None:
        if not self.rival or not self.rival.alive:
            return
        cx, cy = self.cell_center(self.rival.head)
        self.particles.burst(cx, cy, T.rival_head, count=26, speed=210, size=5)
        self.rival.alive = False
        self.rival.respawn_in = 2.6
        if cause != "headon":
            self.kills += 1
            gain = 40 * (2 if Power.DOUBLE in self.effects else 1)
            self.score += gain
            self.shake = max(self.shake, 7.0)
            self.sound.play("kill")

    def respawn_rival(self) -> None:
        taken = self.occupied()
        spots = [(x, y) for x in range(3, COLS - 3) for y in range(2, ROWS - 2)
                 if all((x + i, y) not in taken for i in range(-2, 3))]
        if not spots:
            self.rival.respawn_in = 1.5
            return
        x, y = random.choice(spots)
        self.rival.body = deque([(x, y), (x + 1, y), (x + 2, y)])
        self.rival.prev_body = list(self.rival.body)
        self.rival.direction = LEFT
        self.rival.pending.clear()
        self.rival.grow = 0
        self.rival.alive = True
        cx, cy = self.cell_center((x, y))
        self.particles.ring(cx, cy, T.rival_head, count=16, speed=160)

    def die(self, reason: str) -> None:
        if self.state is State.DEAD:
            return
        self.state = State.DEAD
        self.death_reason = reason
        if self.snake:
            self.snake.alive = False
            cx, cy = self.cell_center(self.snake.head)
            self.particles.burst(cx, cy, T.bad, count=44, speed=260,
                                 size=5, life=0.8)
        self.shake = 17.0
        self.flash, self.flash_color = 0.7, T.bad
        self.sound.play("die")
        self.record_score()

    def record_score(self) -> None:
        table = self.scores.setdefault(self.mode.value, [])
        best = max(table, default=0)
        self.new_record = self.score > best
        table.append(self.score)
        table.sort(reverse=True)
        del table[MAX_SCORES_PER_MODE:]
        save_scores(self.scores)

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def rounded(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
               x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def render(self) -> None:
        self.canvas.delete("all")
        if self.state is State.MENU:
            self.draw_menu()
        elif self.state is State.HELP:
            self.draw_help()
        else:
            self.draw_board()
            self.draw_obstacles()
            self.draw_pickups()
            self.draw_food()
            if self.rival and self.rival.alive:
                self.draw_snake(self.rival, is_rival=True)
            if self.snake:
                self.draw_snake(self.snake)
            self.draw_particles()
            self.draw_flash()
            self.draw_hud()
            if self.state is State.PAUSED:
                self.draw_pause()
            elif self.state is State.DEAD:
                self.draw_gameover()

    # -- board ------------------------------------------------------------- #

    def draw_board(self) -> None:
        c = self.canvas
        ox, oy = self.ox, self.oy + HUD_H
        c.create_rectangle(0, 0, WIN_W, WIN_H, fill=T.bg, outline="")
        c.create_rectangle(ox, oy, ox + BOARD_W, oy + BOARD_H,
                           fill=T.board, outline="")
        for x in range(1, COLS):
            c.create_line(ox + x * CELL, oy, ox + x * CELL, oy + BOARD_H,
                          fill=T.grid)
        for y in range(1, ROWS):
            c.create_line(ox, oy + y * CELL, ox + BOARD_W, oy + y * CELL,
                          fill=T.grid)
        edge = T.accent2 if self.mode is Mode.DUEL else T.panel_edge
        c.create_rectangle(ox, oy, ox + BOARD_W - 1, oy + BOARD_H - 1,
                           outline=edge)

    def draw_obstacles(self) -> None:
        c = self.canvas
        for x, y in self.obstacles:
            px, py = self.ox + x * CELL, self.oy + HUD_H + y * CELL
            self.rounded(px + 1, py + 1, px + CELL - 1, py + CELL - 1, 5,
                         fill=T.wall, outline=T.wall_lit)
            c.create_line(px + 5, py + 5, px + CELL - 6, py + 5,
                          fill=shade(T.wall_lit, 0.12))

    def draw_food(self) -> None:
        c = self.canvas
        for cell in self.foods:
            age = self.food_pop.get(cell, 1.0)
            pop = clamp(age / 0.22, 0.0, 1.0)
            pulse = 1.0 + 0.09 * math.sin(self.clock * 6.0)
            cx, cy = self.cell_center(cell)
            cx += self.ox
            cy += self.oy
            r = CELL * 0.34 * pulse * (0.4 + 0.6 * pop)

            for i in (3, 2, 1):                       # soft glow
                g = r + i * 3.2
                c.create_oval(cx - g, cy - g, cx + g, cy + g,
                              fill=lerp_color(T.board, T.bad, 0.10 * (4 - i)),
                              outline="")
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=T.bad, outline=shade(T.bad, -0.25))
            hr = r * 0.34
            c.create_oval(cx - r * 0.45 - hr, cy - r * 0.45 - hr,
                          cx - r * 0.45 + hr, cy - r * 0.45 + hr,
                          fill=shade(T.bad, 0.55), outline="")
            c.create_line(cx, cy - r, cx + r * 0.55, cy - r * 1.45,
                          fill=T.good, width=2)

    def draw_pickups(self) -> None:
        for p in self.pickups:
            blink = p.ttl < 3.0 and (self.clock * 7) % 1.0 < 0.42
            if blink:
                continue
            px = self.ox + p.cell[0] * CELL
            py = self.oy + HUD_H + p.cell[1] * CELL
            bob = math.sin(self.clock * 4.5 + p.cell[0]) * 1.8
            col = p.kind.color
            self.rounded(px + 3, py + 3 + bob, px + CELL - 3,
                         py + CELL - 3 + bob, 7,
                         fill=lerp_color(T.board, col, 0.30),
                         outline=col)
            self.canvas.create_text(px + CELL / 2, py + CELL / 2 + bob,
                                    text=p.kind.glyph, fill=col,
                                    font=self.f_tiny)

    # -- snakes ------------------------------------------------------------ #

    def snake_points(self, snake: Snake, t: float) -> list[tuple[float, float]]:
        prev = snake.prev_body
        pts = []
        for i, cur in enumerate(snake.body):
            p = prev[i] if i < len(prev) else (prev[-1] if prev else cur)
            if abs(p[0] - cur[0]) > 1 or abs(p[1] - cur[1]) > 1:
                p = cur                              # wrapped: don't slide
            pts.append((lerp(p[0], cur[0], t) + 0.5,
                        lerp(p[1], cur[1], t) + 0.5))
        return pts

    def draw_snake(self, snake: Snake, is_rival: bool = False) -> None:
        c = self.canvas
        t = clamp(self.acc / self.step_time, 0.0, 1.0) \
            if self.state is State.PLAYING else 1.0
        pts = self.snake_points(snake, t)
        if not pts:
            return

        ghost = (not is_rival) and Power.GHOST in self.effects
        n = len(pts)
        w = CELL * 0.80

        def to_px(pt):
            return (self.ox + pt[0] * CELL, self.oy + HUD_H + pt[1] * CELL)

        def body_color(i: int) -> str:
            ratio = 1.0 - (i / max(1, n - 1))
            col = lerp_color(snake.tail_color, snake.head_color, ratio)
            if ghost:
                col = lerp_color(T.board, col, 0.42)
            return col

        # tail -> head so the head lands on top
        for i in range(n - 1, 0, -1):
            a, b = pts[i], pts[i - 1]
            if abs(a[0] - b[0]) > 1.5 or abs(a[1] - b[1]) > 1.5:
                ax, ay = to_px(a)
                r = w / 2
                c.create_oval(ax - r, ay - r, ax + r, ay + r,
                              fill=body_color(i), outline="")
                continue
            ax, ay = to_px(a)
            bx, by = to_px(b)
            width = w * (0.62 + 0.38 * (1.0 - i / max(1, n - 1)))
            c.create_line(ax, ay, bx, by, fill=body_color(i),
                          width=width, capstyle=tk.ROUND)

        # head
        hx, hy = to_px(pts[0])
        hr = w / 2 + 1.5
        head_col = lerp_color(T.board, snake.head_color, 0.45) if ghost \
            else snake.head_color
        c.create_oval(hx - hr, hy - hr, hx + hr, hy + hr,
                      fill=head_col, outline=shade(head_col, -0.35))

        d = snake.direction
        perp = (-d[1], d[0])
        eye_o = hr * 0.42
        eye_f = hr * 0.34
        er = max(2.0, hr * 0.20)
        for sign in (1, -1):
            ex = hx + d[0] * eye_f + perp[0] * eye_o * sign
            ey = hy + d[1] * eye_f + perp[1] * eye_o * sign
            c.create_oval(ex - er, ey - er, ex + er, ey + er,
                          fill="#0a1020", outline="")
            c.create_oval(ex - er * 0.42, ey - er * 0.42,
                          ex + er * 0.1, ey + er * 0.1,
                          fill="#ffffff", outline="")

        if snake.alive and (self.clock * 2.2) % 1.0 < 0.22:     # tongue flick
            tx, ty = hx + d[0] * hr * 1.9, hy + d[1] * hr * 1.9
            c.create_line(hx + d[0] * hr, hy + d[1] * hr, tx, ty,
                          fill=T.bad, width=2)

    def draw_particles(self) -> None:
        c = self.canvas
        for p in self.particles.items:
            k = clamp(p.life / p.max_life, 0.0, 1.0)
            col = lerp_color(T.board, p.color, 0.15 + 0.85 * k)
            s = p.size * (0.35 + 0.65 * k)
            x, y = p.x + self.ox, p.y + self.oy
            c.create_oval(x - s, y - s, x + s, y + s, fill=col, outline="")

    def draw_flash(self) -> None:
        if self.flash <= 0.02:
            return
        stipple = "gray12" if self.flash < 0.25 else \
                  "gray25" if self.flash < 0.5 else "gray50"
        self.canvas.create_rectangle(0, HUD_H, WIN_W, WIN_H,
                                     fill=self.flash_color, outline="",
                                     stipple=stipple)

    # -- HUD --------------------------------------------------------------- #

    def draw_hud(self) -> None:
        c = self.canvas
        c.create_rectangle(0, 0, WIN_W, HUD_H, fill=T.panel, outline="")
        c.create_line(0, HUD_H - 1, WIN_W, HUD_H - 1, fill=T.panel_edge)

        best = max(self.scores.get(self.mode.value, []), default=0)
        best = max(best, self.score)

        def stat(x, label, value, color=T.text, font=None):
            c.create_text(x, 15, text=label, anchor="w", fill=T.muted,
                          font=self.f_label)
            c.create_text(x, 37, text=value, anchor="w", fill=color,
                          font=font or self.f_hud)

        stat(16, "SCORE", f"{self.score}", T.text)
        stat(132, "BEST", f"{best}", T.gold if self.score >= best and best > 0
             else T.muted, self.f_mid)
        stat(226, "LEVEL", f"{self.level}", T.accent, self.f_mid)
        stat(310, "LENGTH", f"{len(self.snake) if self.snake is not None else 0}",
             T.good, self.f_mid)
        mins, secs = divmod(int(self.elapsed), 60)
        stat(404, "TIME", f"{mins}:{secs:02d}", T.text, self.f_mid)
        if self.mode is Mode.DUEL:
            stat(494, "KILLS", f"{self.kills}", T.rival_head, self.f_mid)

        c.create_text(WIN_W - 16, 15, text=self.mode.value.upper(), anchor="e",
                      fill=T.accent2, font=self.f_label)
        hint = "MUTED" if self.sound.muted else "P pause  R restart  M mute"
        c.create_text(WIN_W - 16, HUD_H - 12, text=hint, anchor="e",
                      fill=T.dim, font=self.f_small)

        # combo meter
        cx0, cy0, cx1 = 16, 56, 116
        c.create_rectangle(cx0, cy0, cx1, cy0 + 6, fill=T.bg, outline="")
        if self.combo > 0:
            frac = clamp(self.combo_timer / COMBO_WINDOW, 0.0, 1.0)
            col = lerp_color(T.good, T.gold, (self.combo - 1) / (MAX_COMBO - 1))
            c.create_rectangle(cx0, cy0, cx0 + (cx1 - cx0) * frac, cy0 + 6,
                               fill=col, outline="")
            c.create_text(cx1 + 8, cy0 + 3, text=f"x{self.combo}", anchor="w",
                          fill=col, font=self.f_tiny)

        # active effects
        x = 560 if self.mode is Mode.DUEL else 494
        for power, remaining in self.effects.items():
            total = power.duration or 1.0
            frac = clamp(remaining / total, 0.0, 1.0)
            w = 76
            self.rounded(x, 44, x + w, 66, 6,
                         fill=lerp_color(T.panel, power.color, 0.16),
                         outline=power.color)
            c.create_rectangle(x + 3, 61, x + 3 + (w - 6) * frac, 63,
                               fill=power.color, outline="")
            c.create_text(x + w / 2, 52, text=power.value, fill=power.color,
                          font=self.f_tiny)
            x += w + 7
            if x + w > WIN_W - 10:
                break

    # -- overlays ---------------------------------------------------------- #

    def dim_board(self, stipple: str = "gray50") -> None:
        self.canvas.create_rectangle(0, HUD_H, WIN_W, WIN_H, fill=T.bg,
                                     outline="", stipple=stipple)

    def panel(self, w: int, h: int) -> tuple[float, float]:
        cx, cy = WIN_W / 2, HUD_H + BOARD_H / 2
        self.rounded(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, 16,
                     fill=T.panel, outline=T.panel_edge)
        return cx, cy

    def draw_pause(self) -> None:
        self.dim_board()
        cx, cy = self.panel(360, 190)
        c = self.canvas
        c.create_text(cx, cy - 52, text="PAUSED", fill=T.accent,
                      font=self.f_big)
        c.create_text(cx, cy - 6, text=f"{self.mode.value}  ·  score {self.score}"
                      f"  ·  level {self.level}",
                      fill=T.text, font=self.f_body)
        c.create_text(cx, cy + 30, text="P / Space — resume", fill=T.muted,
                      font=self.f_small)
        c.create_text(cx, cy + 50, text="R — restart        Esc — main menu",
                      fill=T.muted, font=self.f_small)

    def draw_gameover(self) -> None:
        self.dim_board("gray50")
        cx, cy = self.panel(430, 320)
        c = self.canvas

        c.create_text(cx, cy - 122, text="GAME OVER", fill=T.bad,
                      font=self.f_big)
        c.create_text(cx, cy - 92, text=self.death_reason, fill=T.muted,
                      font=self.f_small)

        if self.new_record:
            c.create_text(cx, cy - 62, text="★  NEW HIGH SCORE  ★",
                          fill=T.gold, font=self.f_mid)

        c.create_text(cx, cy - 22, text=str(self.score), fill=T.text,
                      font=self.f_title)
        mins, secs = divmod(int(self.elapsed), 60)
        detail = (f"level {self.level}   ·   {self.eaten} apples   ·   "
                  f"length {len(self.snake) if self.snake is not None else 0}"
                  f"   ·   {mins}:{secs:02d}")
        if self.mode is Mode.DUEL:
            detail += f"   ·   {self.kills} kills"
        c.create_text(cx, cy + 18, text=detail, fill=T.muted,
                      font=self.f_small)

        c.create_text(cx, cy + 48, text=f"BEST — {self.mode.value.upper()}",
                      fill=T.dim, font=self.f_label)
        table = self.scores.get(self.mode.value, [])
        y = cy + 68
        for i, value in enumerate(table[:MAX_SCORES_PER_MODE]):
            hot = value == self.score and self.new_record
            c.create_text(cx, y, text=f"{i + 1}.  {value}",
                          fill=T.gold if hot else T.muted,
                          font=self.f_small)
            y += 18

        c.create_text(cx, cy + 146,
                      text="Enter / R — play again        Esc — main menu",
                      fill=T.accent, font=self.f_small)

    # -- menu -------------------------------------------------------------- #

    def draw_menu(self) -> None:
        c = self.canvas
        c.create_rectangle(0, 0, WIN_W, WIN_H, fill=T.bg, outline="")

        for i in range(28):                            # backdrop wash
            t = i / 27
            c.create_line(0, t * WIN_H, WIN_W, t * WIN_H,
                          fill=lerp_color(T.bg, T.board_alt, 1.0 - t))

        cx = WIN_W / 2
        wob = math.sin(self.clock * 1.6) * 3
        c.create_text(cx + 3, 92 + 3, text="ADVANCED SNAKE", fill=T.accent2,
                      font=self.f_title)
        c.create_text(cx, 92, text="ADVANCED SNAKE", fill=T.text,
                      font=self.f_title)
        c.create_text(cx, 132 + wob * 0.3,
                      text="pick a mode  ·  ↑ ↓ to choose  ·  Enter to play",
                      fill=T.muted, font=self.f_body)

        top = 190
        row_h = 62
        for i, mode in enumerate(Mode):
            y = top + i * row_h
            selected = i == self.menu_index
            x0, x1 = cx - 260, cx + 260
            if selected:
                self.rounded(x0, y - 24, x1, y + 26, 12,
                             fill=lerp_color(T.panel, T.accent, 0.12),
                             outline=T.accent)
            else:
                self.rounded(x0, y - 24, x1, y + 26, 12,
                             fill=T.panel, outline=T.panel_edge)
            c.create_text(x0 + 24, y - 6, text=mode.value, anchor="w",
                          fill=T.text if selected else T.muted,
                          font=self.f_mid)
            c.create_text(x0 + 24, y + 15, text=mode.blurb, anchor="w",
                          fill=T.muted if selected else T.dim,
                          font=self.f_small)
            best = max(self.scores.get(mode.value, []), default=0)
            c.create_text(x1 - 24, y - 6, text=f"best {best}" if best else "—",
                          anchor="e", fill=T.gold if best else T.dim,
                          font=self.f_small)
            if selected:
                c.create_text(x0 - 14, y, text="▶", fill=T.accent,
                              font=self.f_mid)

        c.create_text(cx, WIN_H - 52,
                      text="Arrows / WASD move    ·    P pause    ·    "
                           "H controls & power-ups    ·    M "
                           + ("unmute" if self.sound.muted else "mute"),
                      fill=T.muted, font=self.f_small)
        c.create_text(cx, WIN_H - 30, text="Esc to quit", fill=T.dim,
                      font=self.f_small)

    def draw_help(self) -> None:
        c = self.canvas
        c.create_rectangle(0, 0, WIN_W, WIN_H, fill=T.bg, outline="")
        cx = WIN_W / 2
        c.create_text(cx, 62, text="CONTROLS & POWER-UPS", fill=T.text,
                      font=self.f_big)

        left_x = 70
        y = 130
        c.create_text(left_x, y, text="CONTROLS", anchor="w", fill=T.accent,
                      font=self.f_label)
        y += 26
        for keys, what in (
            ("Arrows / WASD", "steer (turns are buffered)"),
            ("P / Space", "pause & resume"),
            ("R", "restart the current mode"),
            ("M", "mute beeps"),
            ("Esc", "back / quit"),
        ):
            c.create_text(left_x, y, text=keys, anchor="w", fill=T.text,
                          font=self.f_small)
            c.create_text(left_x + 130, y, text=what, anchor="w", fill=T.muted,
                          font=self.f_small)
            y += 22

        y += 18
        c.create_text(left_x, y, text="SCORING", anchor="w", fill=T.accent,
                      font=self.f_label)
        y += 26
        for line in (
            "Apple = (10 + 2 x level) x combo.",
            f"Combo climbs to x{MAX_COMBO} while you keep eating within "
            f"{COMBO_WINDOW:.1f}s.",
            f"Every {FOODS_PER_LEVEL} apples raises the level, "
            "speed, and apple value.",
            "Duel: cutting off the rival is worth 40 points.",
        ):
            c.create_text(left_x, y, text="· " + line, anchor="w", fill=T.muted,
                          font=self.f_small)
            y += 22

        y += 18
        c.create_text(left_x, y, text="POWER-UPS", anchor="w", fill=T.accent,
                      font=self.f_label)
        y += 24
        descriptions = {
            Power.GOLD: "instant 50 x combo points",
            Power.SLOW: "time slows down for 6s",
            Power.GHOST: "phase through walls and yourself for 6.5s",
            Power.SHRINK: "cut 30% of your tail, +4 points per segment",
            Power.MAGNET: "apples come to you for 6s",
            Power.DOUBLE: "all points doubled for 10s",
        }
        for power, text in descriptions.items():
            self.rounded(left_x, y - 9, left_x + 22, y + 13, 6,
                         fill=lerp_color(T.bg, power.color, 0.30),
                         outline=power.color)
            c.create_text(left_x + 11, y + 2, text=power.glyph,
                          fill=power.color, font=self.f_tiny)
            c.create_text(left_x + 36, y + 2, text=power.value, anchor="w",
                          fill=T.text, font=self.f_small)
            c.create_text(left_x + 150, y + 2, text=text, anchor="w",
                          fill=T.muted, font=self.f_small)
            y += 26

        c.create_text(cx, WIN_H - 34, text="Esc / Enter — back to the menu",
                      fill=T.accent, font=self.f_small)


# --------------------------------------------------------------------------- #

def main() -> None:
    root = tk.Tk()
    Game(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()