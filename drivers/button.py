"""Debounced button driver with short and long press detection.

Designed for polling in an asyncio loop. Call update() each iteration
to process state changes. Buttons are assumed active-low with pull-up.
"""

try:
    from time import ticks_diff, ticks_ms  # type: ignore[attr-defined]  # MicroPython
except ImportError:
    from time import time as _time

    def ticks_ms():
        return int(_time() * 1000)

    def ticks_diff(a, b):
        return a - b

# Press event types
EVENT_NONE = 0
EVENT_SHORT = 1
EVENT_LONG = 2


class Button:
    """Debounced button with short/long press detection.

    Usage:
        btn = Button(pin, debounce_ms=50)
        # In your asyncio loop:
        event = btn.update()
        if event == EVENT_SHORT:
            ...
        elif event == EVENT_LONG:
            ...
    """

    def __init__(
        self,
        pin,
        debounce_ms=50,
        short_press_max_ms=1000,
        long_press_min_ms=1500,
        active_low=True,
        _ticks_ms=None,
        _ticks_diff=None,
    ):
        """Initialize button.

        Args:
            pin: machine.Pin instance (should be configured as input with pull-up)
            debounce_ms: Debounce window in milliseconds
            short_press_max_ms: Maximum duration for a short press
            long_press_min_ms: Minimum duration for a long press
            active_low: If True, button reads 0 when pressed (default for pull-up)
            _ticks_ms: Override time.ticks_ms (for testing)
            _ticks_diff: Override time.ticks_diff (for testing)
        """
        self._pin = pin
        self._debounce_ms = debounce_ms
        self._short_max_ms = short_press_max_ms
        self._long_min_ms = long_press_min_ms
        self._active_low = active_low
        self._ticks_ms = _ticks_ms or ticks_ms
        self._ticks_diff = _ticks_diff or ticks_diff

        # State tracking
        self._raw_state = not active_low  # Start as "not pressed"
        self._last_change_ms = self._ticks_ms()
        self._press_start_ms = 0
        self._pressed = False
        self._long_fired = False

    def _is_pressed_raw(self):
        """Read the raw pin state, accounting for active-low logic."""
        val = self._pin.value()
        return (val == 0) if self._active_low else (val == 1)

    @property
    def is_pressed(self):
        """Current debounced pressed state."""
        return self._pressed

    def update(self):
        """Poll button state and return any event.

        Should be called frequently (e.g., every sensor loop iteration).

        Returns:
            EVENT_NONE, EVENT_SHORT, or EVENT_LONG
        """
        now = self._ticks_ms()
        raw = self._is_pressed_raw()

        # Debounce: only accept state change after debounce window
        if raw != self._raw_state:
            self._raw_state = raw
            self._last_change_ms = now

        elapsed_since_change = self._ticks_diff(now, self._last_change_ms)
        if elapsed_since_change < self._debounce_ms:
            return EVENT_NONE

        stable = self._raw_state

        # Detect press start
        if stable and not self._pressed:
            self._pressed = True
            self._press_start_ms = now
            self._long_fired = False
            return EVENT_NONE

        # Detect long press while held
        if stable and self._pressed and not self._long_fired:
            hold_time = self._ticks_diff(now, self._press_start_ms)
            if hold_time >= self._long_min_ms:
                self._long_fired = True
                return EVENT_LONG

        # Detect release
        if not stable and self._pressed:
            self._pressed = False
            hold_time = self._ticks_diff(now, self._press_start_ms)
            if not self._long_fired and hold_time <= self._short_max_ms:
                return EVENT_SHORT

        return EVENT_NONE
