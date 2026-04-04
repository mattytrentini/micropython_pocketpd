"""Polling-based rotary encoder driver with push button.

Uses a Gray code state table to detect rotation direction.
Call update() each loop iteration (e.g., every 33ms).
The push button is handled by a separate Button instance.
"""

# Gray code state transitions for full-step encoder.
# Index by (prev_state << 2 | curr_state), value is delta (-1, 0, +1).
# States: 0b00=0, 0b01=1, 0b10=2, 0b11=3
_TRANSITION_TABLE = (
    #  00   01   10   11  <- current
    0, -1, 1, 0,  # prev=00
    1, 0, 0, -1,  # prev=01
    -1, 0, 0, 1,  # prev=10
    0, 1, -1, 0,  # prev=11
)


class Encoder:
    """Polling-based rotary encoder.

    Usage:
        enc = Encoder(clk_pin, data_pin)
        # In your asyncio loop:
        delta = enc.update()
        if delta != 0:
            value += delta * step_size
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
