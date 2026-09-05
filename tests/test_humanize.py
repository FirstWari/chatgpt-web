import math
import random

from chatgpt_web import humanize as h


def test_path_ends_at_target_and_has_positive_time():
    rng = random.Random(1)
    s = h.new_session(rng)
    pts = h.path((100, 100), (600, 400), 30, s, rng)
    assert len(pts) >= 3
    x, y, _ = pts[-1]
    assert math.hypot(x - 600, y - 400) < 1e-6
    assert all(dt > 0 for _, _, dt in pts)
    total = sum(dt for _, _, dt in pts)
    assert 120 <= total <= 3000


def test_fitts_monotonic_and_floor():
    s = h.Session(a_ms=50, b_ms_per_bit=200)
    assert h.fitts_ms(10, 100, s) == 120.0  # floor
    assert h.fitts_ms(1000, 20, s) > h.fitts_ms(200, 20, s)


def test_min_jerk_bounds():
    assert h.min_jerk(0) == 0 and abs(h.min_jerk(1) - 1) < 1e-9
    assert 0.49 < h.min_jerk(0.5) < 0.51


def test_lognormal_median():
    rng = random.Random(7)
    xs = sorted(h.lognormal_ms(rng, 130, 0.45) for _ in range(4000))
    med = xs[len(xs) // 2]
    assert 115 < med < 145


def test_no_path_for_tiny_moves():
    rng = random.Random(3)
    assert h.path((5, 5), (5.5, 5.2), 10, h.new_session(rng), rng) == []
