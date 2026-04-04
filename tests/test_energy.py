"""Tests for energy accumulation tracker."""

import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

from testutil import assert_eq, assert_near, assert_true

from app.energy import EnergyTracker


class FakeClock:
    def __init__(self, start_ms=0):
        self._now = start_ms

    def ticks_ms(self):
        return self._now

    @staticmethod
    def ticks_diff(a, b):
        return a - b

    def advance(self, ms):
        self._now += ms


def _make_tracker(clock=None):
    if clock is None:
        clock = FakeClock()
    t = EnergyTracker(_ticks_ms=clock.ticks_ms, _ticks_diff=clock.ticks_diff)
    return t, clock


def test_initial_values():
    t, clock = _make_tracker()
    assert_eq(t.wh, 0.0)
    assert_eq(t.ah, 0.0)
    assert_eq(t.elapsed_s, 0.0)


def test_no_accumulation_when_stopped():
    t, clock = _make_tracker()
    t.update(12000, 2000)
    clock.advance(1000)
    t.update(12000, 2000)
    assert_eq(t.wh, 0.0, "should not accumulate when stopped")


def test_accumulation_1hour_at_12v_2a():
    """12V * 2A for 1 hour = 24Wh, 2Ah."""
    t, clock = _make_tracker()
    t.start()
    t.update(12000, 2000)  # First sample sets baseline
    clock.advance(3_600_000)  # 1 hour
    t.update(12000, 2000)
    assert_near(t.wh, 24.0, 0.01, "Wh")
    assert_near(t.ah, 2.0, 0.001, "Ah")
    assert_near(t.elapsed_s, 3600.0, 0.1, "elapsed")


def test_accumulation_small_steps():
    """Multiple small samples should accumulate correctly."""
    t, clock = _make_tracker()
    t.start()
    t.update(5000, 1000)  # 5V 1A
    # 100 steps of 36 seconds = 1 hour
    for _ in range(100):
        clock.advance(36_000)  # 36 seconds
        t.update(5000, 1000)
    assert_near(t.wh, 5.0, 0.01, "5V*1A*1h = 5Wh")
    assert_near(t.ah, 1.0, 0.001, "1A*1h = 1Ah")


def test_stop_pauses_accumulation():
    t, clock = _make_tracker()
    t.start()
    t.update(12000, 2000)
    clock.advance(1_800_000)  # 30 min
    t.update(12000, 2000)
    wh_at_30min = t.wh

    t.stop()
    clock.advance(1_800_000)  # 30 more min
    t.update(12000, 2000)
    assert_eq(t.wh, wh_at_30min, "should not accumulate while stopped")


def test_restart_after_stop():
    t, clock = _make_tracker()
    t.start()
    t.update(12000, 2000)
    clock.advance(1_800_000)
    t.update(12000, 2000)
    wh_at_30min = t.wh

    t.stop()
    clock.advance(600_000)  # 10 min gap
    t.start()
    t.update(12000, 2000)  # Baseline after restart
    clock.advance(1_800_000)  # 30 more min
    t.update(12000, 2000)

    assert_near(t.wh, wh_at_30min * 2, 0.01, "should accumulate after restart")


def test_reset():
    t, clock = _make_tracker()
    t.start()
    t.update(12000, 2000)
    clock.advance(3_600_000)
    t.update(12000, 2000)
    assert_true(t.wh > 0)

    t.reset()
    assert_eq(t.wh, 0.0)
    assert_eq(t.ah, 0.0)
    assert_eq(t.elapsed_s, 0.0)


def test_varying_current():
    """Varying current should accumulate correctly."""
    t, clock = _make_tracker()
    t.start()
    # 10V 1A for 1 hour, then 10V 2A for 1 hour
    t.update(10000, 1000)
    clock.advance(3_600_000)
    t.update(10000, 1000)
    clock.advance(3_600_000)
    t.update(10000, 2000)  # Note: this sample uses 2A but interval was at 1A
    # Total should be ~10Wh (1A) + 10Wh (would be accumulated next, but we only
    # have the endpoint). The tracker uses the *current* reading for the elapsed
    # interval, so second interval still uses previous-sample current.
    # Actually: second update(10000, 1000) at t=1h does 10V*1A*1h=10Wh
    # Third update(10000, 2000) at t=2h does 10V*2A*1h=20Wh (uses current sample's I)
    # Wait, let me re-check the implementation... it uses the current sample's V and I
    # for the elapsed interval. So:
    # Sample at t=0: baseline
    # Sample at t=1h: V=10, I=1, dt=1h → Wh += 10*1*1 = 10
    # Sample at t=2h: V=10, I=2, dt=1h → Wh += 10*2*1 = 20
    # Total = 30Wh
    assert_near(t.wh, 30.0, 0.1, "10Wh + 20Wh")
