"""PocketPD boot — detect hardware and configure I2C bus.

On a real PocketPD board, this finds the AP33772, INA226, and SSD1306 on I2C.
On a bare Pico or without hardware, it reports what was found.
"""

import sys

import machine

import config


def scan_i2c():
    """Scan I2C bus and return set of found addresses."""
    i2c = machine.I2C(
        config.I2C_ID,
        sda=machine.Pin(config.I2C_SDA),
        scl=machine.Pin(config.I2C_SCL),
        freq=config.I2C_FREQ,
    )
    found = set(i2c.scan())
    return i2c, found


def check_hardware(found):
    """Check which PocketPD devices are present."""
    expected = {
        config.ADDR_AP33772: "AP33772 (USB PD)",
        config.ADDR_INA226: "INA226 (Power Monitor)",
        config.ADDR_SSD1306: "SSD1306 (OLED)",
    }
    present = {}
    missing = {}
    for addr, name in expected.items():
        if addr in found:
            present[addr] = name
        else:
            missing[addr] = name
    return present, missing


# Run on import (MicroPython convention for boot.py)
try:
    i2c, found = scan_i2c()
    present, missing = check_hardware(found)

    print("PocketPD boot — I2C scan:")
    for addr, name in present.items():
        print("  [OK]  0x%02x %s" % (addr, name))
    for addr, name in missing.items():
        print("  [--]  0x%02x %s (not found)" % (addr, name))

    if missing:
        print("WARNING: Running with incomplete hardware")

    # Store for main.py
    _boot_i2c = i2c
    _boot_present = present
    _boot_missing = missing
except Exception as e:
    print("Boot error:", e)
    sys.print_exception(e)
    _boot_i2c = None
    _boot_present = {}
    _boot_missing = {}
