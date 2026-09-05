"""Human-like pointer and keyboard input on top of Playwright/Patchright's Input API.

Every event goes through CDP Input.dispatch* (isTrusted=true). Timing/geometry:
- path: cubic Bezier with two lateral control points; time parametrised with the
  minimum-jerk profile s(t) = 10t^3 - 15t^4 + 6t^5 (Flash & Hogan 1985)
- duration: Fitts (Shannon) MT = a + b*log2(D/W + 1); mouse constants from
  MacKenzie, Sellen & Buxton 1991 (a=-107 ms, b=223 ms/bit) resampled per session
  to a ~ U(0, 80) ms, b ~ U(150, 230) ms/bit, MT >= 120 ms
- tremor: N(0, 0.6 px) per sample at 8-16 ms spacing; overshoot p=0.25 when ID > 3 bit
- keys: hold ~ LogNormal(ln 75 ms, 0.30), flight ~ LogNormal(ln 130 ms, 0.45),
  pause after space/punctuation p=0.25 U(300, 800) ms, typo p=1.5 % with backspace
"""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

CURSOR_FILE = "cursor.json"


@dataclass
class Session:
    a_ms: float
    b_ms_per_bit: float
    tremor_px: float = 0.6
    sample_ms: tuple[int, int] = (8, 16)


def new_session(rng: random.Random | None = None) -> Session:
    r = rng or random
    return Session(a_ms=r.uniform(0, 80), b_ms_per_bit=r.uniform(150, 230))


# ------------------------------------------------------------------ math ----
def fitts_ms(dist: float, width: float, s: Session) -> float:
    width = max(width, 4.0)
    idx = math.log2(dist / width + 1.0)
    return max(120.0, s.a_ms + s.b_ms_per_bit * idx)


def min_jerk(tau: float) -> float:
    return 10 * tau**3 - 15 * tau**4 + 6 * tau**5


def bezier(p0, p1, p2, p3, t: float):
    u = 1 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return x, y


def control_points(p0, p3, rng: random.Random):
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d  # unit normal
    k1 = rng.uniform(-0.20, 0.20)
    k2 = rng.uniform(-0.20, 0.20)
    if rng.random() < 0.7:  # single arc most of the time
        k2 = math.copysign(abs(k2), k1)
    p1 = (p0[0] + 0.30 * dx + nx * k1 * d, p0[1] + 0.30 * dy + ny * k1 * d)
    p2 = (p0[0] + 0.70 * dx + nx * k2 * d, p0[1] + 0.70 * dy + ny * k2 * d)
    return p1, p2


def path(p0, p3, width: float, s: Session, rng: random.Random) -> list[tuple[float, float, float]]:
    """Samples (x, y, dt_ms) from p0 to p3 including optional overshoot+correction."""
    out: list[tuple[float, float, float]] = []
    d = math.hypot(p3[0] - p0[0], p3[1] - p0[1])
    if d < 1.0:
        return out
    idx = math.log2(d / max(width, 4.0) + 1.0)
    target = p3
    overshoot = idx > 3.0 and rng.random() < 0.25
    if overshoot:
        f = rng.uniform(0.03, 0.08)
        target = (p3[0] + (p3[0] - p0[0]) * f, p3[1] + (p3[1] - p0[1]) * f)
    out += _segment(p0, target, fitts_ms(d, width, s), s, rng)
    if overshoot:
        out += _segment(target, p3, rng.uniform(80, 150), s, rng, tremor=0.3)
    return out


def _segment(p0, p3, mt_ms: float, s: Session, rng: random.Random, tremor: float | None = None):
    p1, p2 = control_points(p0, p3, rng)
    n = max(3, int(mt_ms / rng.uniform(*s.sample_ms)))
    tr = s.tremor_px if tremor is None else tremor
    pts = []
    for i in range(1, n + 1):
        tau = i / n
        x, y = bezier(p0, p1, p2, p3, min_jerk(tau))
        if i < n:
            x += rng.gauss(0, tr)
            y += rng.gauss(0, tr)
        pts.append((x, y, mt_ms / n))
    return pts


def lognormal_ms(rng: random.Random, median_ms: float, sigma: float) -> float:
    return rng.lognormvariate(math.log(median_ms), sigma)


# ---------------------------------------------------------- browser glue ----
class Human:
    """Bind to a Playwright page. Keeps the cursor position across processes (cursor.json)."""

    def __init__(self, page, state_dir: Path, seed: int | None = None):
        self.page = page
        self.rng = random.Random(seed)
        self.s = new_session(self.rng)
        self.state_file = Path(state_dir) / CURSOR_FILE
        self.pos = self._load_pos()

    def _load_pos(self):
        try:
            d = json.loads(self.state_file.read_text())
            return (float(d["x"]), float(d["y"]))
        except Exception:  # noqa: BLE001
            vs = self.page.viewport_size or {"width": 1280, "height": 720}
            return (vs["width"] * self.rng.uniform(0.3, 0.7), vs["height"] * self.rng.uniform(0.3, 0.7))

    def _save_pos(self):
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({"x": self.pos[0], "y": self.pos[1]}))
        except OSError:
            pass

    def think(self, median_ms: float = 220, sigma: float = 0.35):
        time.sleep(lognormal_ms(self.rng, median_ms, sigma) / 1000)

    def move_to(self, x: float, y: float, width: float = 20.0):
        for px, py, dt in path(self.pos, (x, y), width, self.s, self.rng):
            self.page.mouse.move(px, py)
            time.sleep(dt / 1000)
        self.page.mouse.move(x, y)
        self.pos = (x, y)
        self._save_pos()

    def click_locator(self, locator, timeout: float = 15000, x_frac: float | None = None):
        locator.wait_for(state="visible", timeout=timeout)
        try:
            locator.scroll_into_view_if_needed(timeout=timeout)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(self.rng.uniform(0.2, 0.6))
        box = locator.bounding_box()
        if not box:
            locator.click()
            return
        # aim inside the element, biased to the centre (clipped normal)
        cx = box["x"] + box["width"] * (x_frac if x_frac is not None else 0.5)
        spread = box["width"] / 6 if x_frac is None else box["width"] / 12
        x = cx + max(-box["width"] * 0.4, min(box["width"] * 0.4, self.rng.gauss(0, spread)))
        x = min(max(x, box["x"] + 2), box["x"] + box["width"] - 2)
        y = box["y"] + box["height"] / 2 + max(-box["height"] * 0.4, min(box["height"] * 0.4, self.rng.gauss(0, box["height"] / 6)))
        self.think()
        self.move_to(x, y, width=min(box["width"], box["height"]))
        time.sleep(self.rng.uniform(0.03, 0.12))
        self.page.mouse.down()
        time.sleep(lognormal_ms(self.rng, 85, 0.25) / 1000)
        self.page.mouse.up()

    def type_text(self, text: str, typo_rate: float = 0.015):
        kb = self.page.keyboard
        neighbours = "qwertyuiopasdfghjklzxcvbnm"
        for ch in text:
            if ch.isalpha() and self.rng.random() < typo_rate:
                wrong = self.rng.choice(neighbours)
                kb.press(wrong.upper() if ch.isupper() else wrong) if wrong.isalpha() else kb.type(wrong)
                time.sleep(self.rng.uniform(0.2, 0.4))
                kb.press("Backspace")
                time.sleep(lognormal_ms(self.rng, 130, 0.45) / 1000)
            if ch == "\n":
                kb.down("Shift")
                kb.press("Enter")
                kb.up("Shift")
            else:
                kb.type(ch, delay=lognormal_ms(self.rng, 75, 0.30))
            time.sleep(lognormal_ms(self.rng, 130, 0.45) / 1000)
            if ch in " .,;:!?\n" and self.rng.random() < 0.25:
                time.sleep(self.rng.uniform(0.3, 0.8))

    def paste_text(self, text: str):
        """Long text: humans paste. Chromium's insert_text arrives as one input event like a paste."""
        time.sleep(self.rng.uniform(0.3, 0.9))
        self.page.keyboard.insert_text(text)
        time.sleep(self.rng.uniform(0.4, 1.2))
