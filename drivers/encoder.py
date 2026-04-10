"""Rotary encoder driver with interrupt and polling backends.

IRQ-based (default on RP2040):
    Uses miketeachman/micropython-rotary for interrupt-driven detection.
    Much more responsive than polling — no missed steps.

Polling fallback (sim/tests):
    Gray code state table, call update() each loop iteration.

Both expose the same interface: update() returns delta, value/reset for state.
"""


class Encoder:
    """IRQ-based rotary encoder using micropython-rotary.

    Wraps RotaryIRQ to provide the same delta-based update() interface
    the state machine expects.
    """

    def __init__(self, clk_pin_num, data_pin_num):
        """Initialize IRQ-based encoder.

        Args:
            clk_pin_num: GPIO number for encoder CLK (A) signal
            data_pin_num: GPIO number for encoder DATA (B) signal
        """
        from rotary_irq_rp2 import RotaryIRQ

        self._rotary = RotaryIRQ(
            pin_num_clk=clk_pin_num,
            pin_num_dt=data_pin_num,
            range_mode=RotaryIRQ.RANGE_UNBOUNDED,
            pull_up=False,
            half_step=False,
        )
        self._last_value = self._rotary.value()

    @property
    def value(self):
        """Current accumulated encoder value."""
        return self._rotary.value()

    @value.setter
    def value(self, val):
        self._rotary.set(value=val)
        self._last_value = val

    def update(self):
        """Return rotation delta since last call.

        Returns:
            Negative for counter-clockwise, 0 for no change, positive for clockwise
        """
        current = self._rotary.value()
        delta = current - self._last_value
        self._last_value = current
        return delta

    def reset(self):
        """Reset accumulated value to zero."""
        self._rotary.reset()
        self._last_value = 0


# --- Polling fallback for sim/tests (no IRQ support in mock_machine) ---

# Gray code state transitions for full-step encoder.
# Index by (prev_state << 2 | curr_state), value is delta (-1, 0, +1).
_TRANSITION_TABLE = (
    #  00   01   10   11  <- current
    0, -1, 1, 0,  # prev=00
    1, 0, 0, -1,  # prev=01
    -1, 0, 0, 1,  # prev=10
    0, 1, -1, 0,  # prev=11
)


class PollingEncoder:
    """Polling-based rotary encoder for simulation and tests.

    Usage:
        enc = PollingEncoder(clk_pin, data_pin)
        # In your asyncio loop:
        delta = enc.update()
    """

    def __init__(self, clk_pin, data_pin):
        """Initialize encoder.

        Args:
            clk_pin: machine.Pin for encoder CLK (A) signal
            data_pin: machine.Pin for encoder DATA (B) signal
        """
        self._clk = clk_pin
        self._data = data_pin

        # Read initial state
        self._state = (self._clk.value() << 1) | self._data.value()
        self._value = 0

    @property
    def value(self):
        """Current accumulated encoder value."""
        return self._value

    @value.setter
    def value(self, val):
        self._value = val

    def update(self):
        """Read encoder pins and return rotation delta since last call.

        Returns:
            -1 for counter-clockwise, 0 for no change, +1 for clockwise
        """
        new_state = (self._clk.value() << 1) | self._data.value()
        if new_state == self._state:
            return 0

        index = (self._state << 2) | new_state
        delta = _TRANSITION_TABLE[index]
        self._state = new_state

        self._value += delta
        return delta

    def reset(self):
        """Reset accumulated value to zero."""
        self._value = 0
