"""Tests for PocketPD state machine."""

import struct
import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/lib")
sys.path.insert(0, "/code/tests")

import framebuf
import machine
from testutil import assert_eq, assert_false, assert_true

from app.settings import Settings
from app.state_machine import (
    STATE_BOOT,
    STATE_CAPDISPLAY,
    STATE_MENU,
    STATE_NORMAL_PDO,
    STATE_NORMAL_PPS,
    STATE_OBTAIN,
    StateMachine,
)
from drivers.ap33772 import AP33772, STATUS_READY
from drivers.button import EVENT_NONE, Button
from drivers.display import Display
from drivers.encoder import PollingEncoder as Encoder
from drivers.ina226 import INA226


class FakeClock:
    def __init__(self):
        self._now = 0

    def ticks_ms(self):
        return self._now

    @staticmethod
    def ticks_diff(a, b):
        return a - b

    def advance(self, ms):
        self._now += ms


class FakeDisplayDevice(framebuf.FrameBuffer):
    def __init__(self):
        self.width = 128
        self.height = 64
        self.buffer = bytearray(128 * 64 // 8)
        super().__init__(self.buffer, 128, 64, framebuf.MONO_VLSB)

    def show(self):
        pass


def _make_fixed_pdo_bytes(voltage_mv, max_current_ma):
    dword = ((voltage_mv // 50) & 0x3FF) << 10
    dword |= (max_current_ma // 10) & 0x3FF
    return struct.pack("<I", dword)


def _make_pps_pdo_bytes(min_voltage_mv, max_voltage_mv, max_current_ma):
    dword = 0b11 << 30
    dword |= ((max_voltage_mv // 100) & 0xFF) << 17
    dword |= ((min_voltage_mv // 100) & 0xFF) << 8
    dword |= (max_current_ma // 50) & 0x7F
    return struct.pack("<I", dword)


def _make_state_machine(with_pps=True):
    """Build a fully wired state machine with mock hardware."""
    clock = FakeClock()

    # Mock I2C with AP33772 and INA226
    i2c = machine.I2C(0)

    # AP33772 mock device
    pdos = [
        _make_fixed_pdo_bytes(5000, 3000),
        _make_fixed_pdo_bytes(9000, 3000),
        _make_fixed_pdo_bytes(20000, 3250),
    ]
    if with_pps:
        pdos.append(_make_pps_pdo_bytes(3300, 21000, 5000))

    pdo_data = b""
    for p in pdos:
        pdo_data += p

    pd_dev = machine.I2CDevice(addr=0x51, i2c=i2c)
    pd_dev.register_values[0x00] = pdo_data
    pd_dev.register_values[0x1C] = bytes([len(pdos)])
    pd_dev.register_values[0x1D] = bytes([STATUS_READY])
    pd_dev.register_values[0x1E] = bytes([0])
    pd_dev.register_values[0x20] = bytes([63])  # ~5V (63*80mV)
    pd_dev.register_values[0x21] = bytes([42])  # ~1A (42*24mA)
    pd_dev.register_values[0x22] = bytes([25])
    pd_dev.register_values[0x30] = bytes(4)

    # INA226 mock device
    ina_dev = machine.I2CDevice(addr=0x40, i2c=i2c)
    for reg in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
        ina_dev.register_values[reg] = bytes(2)
    ina_dev.register_values[0x02] = struct.pack(">H", 4000)  # 5V
    ina_dev.register_values[0x04] = struct.pack(">h", 5958)  # ~1A
    ina_dev.register_values[0xFE] = struct.pack(">H", 0x5449)
    ina_dev.register_values[0xFF] = struct.pack(">H", 0x2260)

    pd = AP33772(i2c, addr=0x51)
    ina = INA226(i2c, addr=0x40)
    ina.init()

    display = Display(FakeDisplayDevice())

    btn_output = Button(
        machine.Pin(10, machine.Pin.IN, value=1),
        _ticks_ms=clock.ticks_ms, _ticks_diff=clock.ticks_diff,
    )
    btn_select = Button(
        machine.Pin(11, machine.Pin.IN, value=1),
        _ticks_ms=clock.ticks_ms, _ticks_diff=clock.ticks_diff,
    )
    btn_encoder = Button(
        machine.Pin(18, machine.Pin.IN, value=1),
        _ticks_ms=clock.ticks_ms, _ticks_diff=clock.ticks_diff,
    )
    encoder = Encoder(
        machine.Pin(19, machine.Pin.IN, value=1),
        machine.Pin(20, machine.Pin.IN, value=1),
    )
    output_pin = machine.Pin(1, machine.Pin.OUT, value=0)

    settings = Settings("/tmp/test_sm_settings.json")

    sm = StateMachine(
        display=display, ap33772=pd, ina226=ina,
        btn_output=btn_output, btn_select=btn_select, btn_encoder=btn_encoder,
        encoder=encoder, output_pin=output_pin, settings=settings,
        _ticks_ms=clock.ticks_ms, _ticks_diff=clock.ticks_diff,
    )

    return sm, clock


# --- State transition tests ---


def test_initial_state_is_boot():
    sm, clock = _make_state_machine()
    assert_eq(sm.state, STATE_BOOT)


def test_boot_renders():
    sm, clock = _make_state_machine()
    sm.handle_boot()
    # Should not crash


def test_obtain_reads_pdos():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    assert_true(len(sm.pd.fixed_pdos) > 0, "should have parsed fixed PDOs")
    assert_true(sm.pd.has_pps, "should have PPS")


def test_enter_normal_pps():
    sm, clock = _make_state_machine(with_pps=True)
    sm.handle_obtain()
    sm._enter_normal()
    assert_eq(sm.state, STATE_NORMAL_PPS)


def test_enter_normal_pdo_only():
    sm, clock = _make_state_machine(with_pps=False)
    sm.handle_obtain()
    sm._enter_normal()
    assert_eq(sm.state, STATE_NORMAL_PDO)


# --- Output control ---


def test_output_toggle():
    sm, clock = _make_state_machine()
    assert_false(sm.output_on)
    sm.set_output(True)
    assert_true(sm.output_on)
    sm.set_output(False)
    assert_false(sm.output_on)


def test_output_pin_follows():
    sm, clock = _make_state_machine()
    sm.set_output(True)
    assert_eq(sm.output_pin.value(), 1)
    sm.set_output(False)
    assert_eq(sm.output_pin.value(), 0)


# --- Sensor reading ---


def test_read_sensors():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    sm._enter_normal()
    sm.read_sensors()
    assert_true(sm.voltage_mv > 0, "should read voltage")


# --- Normal display ---


def test_handle_normal_renders():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    sm._enter_normal()
    sm.handle_normal()
    # Should not crash


def test_handle_normal_energy_mode():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    sm._enter_normal()
    sm.display_energy = True
    sm.handle_normal()
    # Should not crash


# --- Menu ---


def test_build_menu():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    sm._build_menu()
    assert_true(len(sm._menu_profiles) > 0)


def test_menu_state():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    sm._enter_normal()
    sm._build_menu()
    sm._set_state(STATE_MENU)
    sm.handle_menu()
    # Should not crash


# --- CV/CC detection ---


def test_cv_mode_default():
    sm, clock = _make_state_machine()
    sm.detect_cv_cc()
    assert_true(sm.cv_mode)


def test_cc_detection():
    sm, clock = _make_state_machine()
    sm.handle_obtain()
    sm._set_state(STATE_NORMAL_PPS)
    sm.output_on = True
    sm.settings.target_voltage_mv = 12000
    sm.settings.target_current_ma = 1000
    # Measured V well below target, current near target → CC
    sm.voltage_mv = 8000
    sm.current_ma = 950
    sm.detect_cv_cc()
    assert_false(sm.cv_mode, "should detect CC mode")
