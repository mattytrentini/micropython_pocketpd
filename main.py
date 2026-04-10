"""PocketPD main — wire up drivers and run the state machine."""

import asyncio

import machine

import config
from app.settings import Settings
from app.state_machine import StateMachine
from drivers.ap33772 import AP33772
from drivers.button import Button
from drivers.encoder import Encoder
from drivers.ina226 import INA226


def create_app():
    """Create and wire up all components."""
    # Create I2C bus (boot.py already ran a diagnostic scan, but we create
    # a fresh instance here to avoid double-init issues)
    i2c = machine.I2C(
        config.I2C_ID,
        sda=machine.Pin(config.I2C_SDA),
        scl=machine.Pin(config.I2C_SCL),
        freq=config.I2C_FREQ,
    )
    present = set(i2c.scan())

    # Display
    has_display = config.ADDR_SSD1306 in present
    if has_display:
        from drivers.display import Display
        from lib.ssd1306 import SSD1306_I2C

        ssd = SSD1306_I2C(128, 64, i2c)
        display = Display(ssd)
    else:
        display = _NullDisplay()

    # PD controller
    pd = AP33772(i2c, addr=config.ADDR_AP33772)

    # Power monitor
    ina = INA226(i2c, addr=config.ADDR_INA226)
    ina.init()

    # Buttons (active-low with pull-up)
    btn_output = Button(
        machine.Pin(config.PIN_BTN_OUTPUT, machine.Pin.IN, machine.Pin.PULL_UP),
        debounce_ms=config.DEBOUNCE_MS,
        short_press_max_ms=config.SHORT_PRESS_MAX_MS,
        long_press_min_ms=config.LONG_PRESS_MIN_MS,
    )
    btn_select = Button(
        machine.Pin(config.PIN_BTN_SELECT, machine.Pin.IN, machine.Pin.PULL_UP),
        debounce_ms=config.DEBOUNCE_MS,
        short_press_max_ms=config.SHORT_PRESS_MAX_MS,
        long_press_min_ms=config.LONG_PRESS_MIN_MS,
    )
    btn_encoder = Button(
        machine.Pin(config.PIN_ENC_SW, machine.Pin.IN, machine.Pin.PULL_UP),
        debounce_ms=config.DEBOUNCE_MS,
        short_press_max_ms=config.SHORT_PRESS_MAX_MS,
        long_press_min_ms=config.LONG_PRESS_MIN_MS,
    )

    # Rotary encoder (IRQ-based — takes GPIO numbers, not Pin objects)
    encoder = Encoder(
        config.PIN_ENC_CLK,
        config.PIN_ENC_DATA,
    )

    # Output enable pin (default off)
    output_pin = machine.Pin(config.PIN_OUTPUT_EN, machine.Pin.OUT, value=0)

    # Settings
    settings = Settings()

    # State machine
    sm = StateMachine(
        display=display,
        ap33772=pd,
        ina226=ina,
        btn_output=btn_output,
        btn_select=btn_select,
        btn_encoder=btn_encoder,
        encoder=encoder,
        output_pin=output_pin,
        settings=settings,
    )

    return sm


class _NullDisplay:
    """No-op display for when SSD1306 is not connected."""

    width = 128
    height = 64

    def clear(self):
        pass

    def show(self):
        pass

    def text_large(self, *a):
        pass

    def text_medium(self, *a):
        pass

    def text_small(self, *a):
        pass

    def hline(self, *a):
        pass

    def vline(self, *a):
        pass

    def rect(self, *a):
        pass

    def fill_rect(self, *a):
        pass

    def pixel(self, *a):
        pass

    @property
    def device(self):
        return self


def main():
    print("PocketPD starting...")
    sm = create_app()
    asyncio.run(sm.run())


main()
