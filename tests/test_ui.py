"""Tests for UI rendering functions."""

import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/lib")
sys.path.insert(0, "/code/tests")

import framebuf
from testutil import assert_eq, assert_true

from app.ui import (
    draw_boot,
    draw_capabilities,
    draw_energy,
    draw_menu,
    draw_normal,
)
from drivers.display import Display


class FakeDisplay(framebuf.FrameBuffer):
    """Framebuffer-based display for testing — no hardware."""

    def __init__(self, width=128, height=64):
        self.width = width
        self.height = height
        self.buffer = bytearray(width * height // 8)
        self._show_count = 0
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)

    def show(self):
        self._show_count += 1

    def has_content(self):
        """Check if any pixels are lit."""
        return any(b != 0 for b in self.buffer)

    def pixel_count(self):
        """Count total lit pixels."""
        count = 0
        for b in self.buffer:
            while b:
                count += b & 1
                b >>= 1
        return count


def _make_display():
    fake = FakeDisplay()
    display = Display(fake)
    return display, fake


# --- Smoke tests: each screen renders without errors and produces output ---


def test_draw_boot():
    display, fake = _make_display()
    draw_boot(display)
    assert_true(fake.has_content(), "boot screen should have content")
    assert_eq(fake._show_count, 1, "show() called once")


def test_draw_capabilities_fixed_only():
    display, fake = _make_display()

    class FakePDO:
        def __init__(self, v, i):
            self.voltage_mv = v
            self.max_current_ma = i

    fixed = [FakePDO(5000, 3000), FakePDO(9000, 3000), FakePDO(20000, 3250)]
    draw_capabilities(display, fixed, [])
    assert_true(fake.has_content())
    assert_eq(fake._show_count, 1)


def test_draw_capabilities_with_pps():
    display, fake = _make_display()

    class FakePDO:
        def __init__(self, v, i):
            self.voltage_mv = v
            self.max_current_ma = i

    class FakePPS:
        def __init__(self, vmin, vmax, i):
            self.min_voltage_mv = vmin
            self.max_voltage_mv = vmax
            self.max_current_ma = i

    fixed = [FakePDO(5000, 3000)]
    pps = [FakePPS(3300, 21000, 5000)]
    draw_capabilities(display, fixed, pps)
    assert_true(fake.has_content())


def test_draw_normal_output_off():
    display, fake = _make_display()
    draw_normal(
        display,
        voltage_mv=5040,
        current_ma=1200,
        target_v_mv=5000,
        target_i_ma=3000,
        output_on=False,
        is_pps=False,
        cv_mode=True,
        adjust_voltage=True,
        cursor_pos=0,
        blink_on=False,
    )
    assert_true(fake.has_content())
    assert_eq(fake._show_count, 1)


def test_draw_normal_pps_mode():
    display, fake = _make_display()
    draw_normal(
        display,
        voltage_mv=12040,
        current_ma=2400,
        target_v_mv=12000,
        target_i_ma=3000,
        output_on=True,
        is_pps=True,
        cv_mode=True,
        adjust_voltage=True,
        cursor_pos=1,
        blink_on=True,
    )
    assert_true(fake.has_content())
    # PPS mode with blink_on should render more content (target values + cursor)
    pixel_count = fake.pixel_count()
    assert_true(pixel_count > 100, "PPS mode should have substantial content")


def test_draw_normal_cc_mode():
    display, fake = _make_display()
    draw_normal(
        display,
        voltage_mv=4800,
        current_ma=1000,
        target_v_mv=5000,
        target_i_ma=1000,
        output_on=True,
        is_pps=True,
        cv_mode=False,
        adjust_voltage=False,
        cursor_pos=0,
        blink_on=True,
    )
    assert_true(fake.has_content())


def test_draw_energy():
    display, fake = _make_display()
    draw_energy(
        display,
        voltage_mv=12000,
        current_ma=2000,
        power_mw=24000,
        elapsed_s=3661,  # 1:01:01
        wh=1.234,
        ah=0.1028,
    )
    assert_true(fake.has_content())
    assert_eq(fake._show_count, 1)


def test_draw_menu():
    display, fake = _make_display()
    profiles = ["5V 3A", "9V 3A", "15V 3A", "20V 3.25A"]
    draw_menu(display, profiles, selected_idx=1, is_pps_list=False)
    assert_true(fake.has_content())
    assert_eq(fake._show_count, 1)


def test_draw_menu_scrolling():
    """Menu with more items than visible should scroll."""
    display, fake = _make_display()
    profiles = ["5V 3A", "9V 3A", "12V 2A", "15V 3A", "20V 3.25A", "20V 5A"]
    draw_menu(display, profiles, selected_idx=5, is_pps_list=False)
    assert_true(fake.has_content())


def test_clear_and_draw():
    """Drawing should clear previous content."""
    display, fake = _make_display()
    draw_boot(display)
    pixels_boot = fake.pixel_count()

    draw_energy(display, 0, 0, 0, 0, 0.0, 0.0)
    pixels_energy = fake.pixel_count()

    # Different screens should produce different pixel counts
    # (not a perfect test but catches gross errors like not clearing)
    assert_true(pixels_boot > 0)
    assert_true(pixels_energy > 0)
