"""Energy accumulation tracker — Wh and Ah from timestamped V*I samples."""

try:
    from time import ticks_diff, ticks_ms  # type: ignore[attr-defined]
except ImportError:
    from time import time as _time

    def ticks_ms():
        return int(_time() * 1000)

    def ticks_diff(a, b):
        return a - b


class EnergyTracker:
    """Accumulates Wh and Ah from periodic voltage/current samples."""

    def __init__(self, _ticks_ms=None, _ticks_diff=None):
        self._ticks_ms = _ticks_ms or ticks_ms
        self._ticks_diff = _ticks_diff or ticks_diff
        self.wh = 0.0
        self.ah = 0.0
        self.elapsed_s = 0.0
        self._last_ms = None
        self._running = False

    def start(self):
        """Start or resume accumulation."""
        self._last_ms = self._ticks_ms()
        self._running = True

    def stop(self):
        """Pause accumulation."""
        self._running = False
        self._last_ms = None

    def reset(self):
        """Reset all accumulated values."""
        self.wh = 0.0
        self.ah = 0.0
        self.elapsed_s = 0.0
        self._last_ms = None

    def update(self, voltage_mv, current_ma):
        """Add a sample to the accumulation.

        Should be called each sensor loop iteration while output is on.

        Args:
            voltage_mv: Measured voltage in millivolts
            current_ma: Measured current in milliamps
        """
        if not self._running:
            return

        now = self._ticks_ms()
        if self._last_ms is None:
            self._last_ms = now
            return

        dt_ms = self._ticks_diff(now, self._last_ms)
        self._last_ms = now

        if dt_ms <= 0:
            return

        dt_h = dt_ms / 3_600_000  # ms to hours
        dt_s = dt_ms / 1000

        voltage_v = voltage_mv / 1000
        current_a = current_ma / 1000

        self.wh += voltage_v * current_a * dt_h
        self.ah += current_a * dt_h
        self.elapsed_s += dt_s

    @property
    def power_mw(self):
        """Not tracked — compute from latest V*I externally."""
        return 0
