"""PocketPD simulation entry point.

Runs the full PocketPD application under MicroPython Unix port with:
- Simulated I2C devices (AP33772 + INA226)
- Browser-rendered OLED display via framebuf_canvas
- REST API + WebSocket for control and monitoring

Usage:
    docker run --rm -p 8080:8080 -v $(pwd):/code -w /code micropython/unix \
        micropython sim/main_sim.py
    Then open http://localhost:8080
"""

import sys

# Set up module paths — /code must be first for lib.* package imports to work
# IMPORTANT: don't add /code/lib/mock_machine directly — its own lib/ dir
# shadows our lib/ package. Instead, import mock_machine.py by direct path.
sys.path.insert(0, "/code")
sys.path.insert(0, "/code/lib/framebuf_canvas")  # for framebuf_canvas package
# microdot is a package at lib/framebuf_canvas/microdot/ — its parent is already in path

# Install logging (needed by mock_machine) into a temp location
import mip

mip.install("logging", target="/tmp/mip_lib")
sys.path.insert(0, "/tmp/mip_lib")

# Bootstrap mock_machine for Pin/I2C simulation
# Import from lib.mock_machine as a package, then register manually
# register_as_machine() expects mock_machine in sys.modules by its short name
import sys as _sys

from lib.mock_machine import mock_machine

_sys.modules["mock_machine"] = mock_machine
mock_machine.register_as_machine()

import asyncio

import machine
from framebuf_canvas import MONO_VLSB, DisplayServer, FrameBuffer

import config
from app.settings import Settings
from app.state_machine import StateMachine
from drivers.ap33772 import AP33772
from drivers.button import Button
from drivers.display import Display
from drivers.encoder import Encoder
from drivers.ina226 import INA226
from sim.devices import SimAP33772, SimINA226
from sim.server import add_status_snapshot, setup_routes


def create_sim():
    """Create the full simulation environment."""
    print("Creating simulated PocketPD...")

    # Simulated I2C devices
    i2c = machine.I2C(0)
    sim_ap = SimAP33772(i2c)
    sim_ina = SimINA226(i2c)

    # Display via framebuf_canvas
    buf = bytearray(128 * 64 // 8)
    sim_fb = FrameBuffer(buf, 128, 64, MONO_VLSB)

    # Wrap show() to also flush to WebSocket
    _original_show = getattr(sim_fb, "show", None)

    def show_and_flush():
        if _original_show:
            _original_show()
        sim_fb.flush()

    sim_fb.show = show_and_flush

    display = Display(sim_fb)

    # Web server
    server = DisplayServer(port=8080, static_path="/code/sim/static")
    server.register(sim_fb)

    # Drivers (using mock I2C)
    pd = AP33772(i2c, addr=config.ADDR_AP33772)
    ina = INA226(i2c, addr=config.ADDR_INA226)
    ina.init()

    # Buttons (mock pins, not pressed)
    btn_output = Button(machine.Pin(config.PIN_BTN_OUTPUT, machine.Pin.IN, value=1))
    btn_select = Button(machine.Pin(config.PIN_BTN_SELECT, machine.Pin.IN, value=1))
    btn_encoder = Button(machine.Pin(config.PIN_ENC_SW, machine.Pin.IN, value=1))

    # Encoder (mock pins)
    encoder = Encoder(
        machine.Pin(config.PIN_ENC_CLK, machine.Pin.IN, value=1),
        machine.Pin(config.PIN_ENC_DATA, machine.Pin.IN, value=1),
    )

    # Output pin (mock)
    output_pin = machine.Pin(config.PIN_OUTPUT_EN, machine.Pin.OUT, value=0)

    # Settings
    settings = Settings("/tmp/pocketpd_sim_settings.json")

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

    # Add status snapshot method
    add_status_snapshot(sm)

    # Add REST API and WebSocket routes
    broadcast_status = setup_routes(server.app, sm, sim_ina=sim_ina)

    return server, sm, sim_ap, sim_ina, broadcast_status


async def run_sim(server, sm, sim_ap, sim_ina, broadcast_status):
    """Run the simulation — web server + state machine concurrently."""
    print("Starting PocketPD simulation at http://0.0.0.0:8080")

    async def sim_sync_loop():
        """Periodically sync simulated device state."""
        while True:
            sim_ap.update()
            sim_ina.track_ap33772(sim_ap)
            sim_ina.set_output(sm.output_on)
            await broadcast_status()
            await asyncio.sleep(0.1)

    # Run web server, state machine, and sim sync concurrently
    # server.start() is an async coroutine that runs the HTTP server
    await asyncio.gather(
        server.start(),
        sm.run(),
        sim_sync_loop(),
    )


def main():
    server, sm, sim_ap, sim_ina, broadcast_status = create_sim()
    asyncio.run(run_sim(server, sm, sim_ap, sim_ina, broadcast_status))


main()
