"""INA226 current/voltage/power monitor driver.

Communicates via I2C with 16-bit big-endian registers.
Calibrated for PocketPD HW1.1+ with 5mΩ shunt resistor.

Reference: Texas Instruments INA226 datasheet (SBOS547A)
"""

import struct

# Register addresses
_REG_CONFIG = 0x00
_REG_SHUNT_VOLTAGE = 0x01
_REG_BUS_VOLTAGE = 0x02
_REG_POWER = 0x03
_REG_CURRENT = 0x04
_REG_CALIBRATION = 0x05
_REG_MASK_ENABLE = 0x06
_REG_ALERT_LIMIT = 0x07
_REG_MANUFACTURER_ID = 0xFE
_REG_DIE_ID = 0xFF

# Expected ID values
MANUFACTURER_ID = 0x5449
DIE_ID = 0x2260

# Configuration register bit fields
# Averaging mode (bits 11:9)
AVG_1 = 0x0000
AVG_4 = 0x0200
AVG_16 = 0x0400
AVG_64 = 0x0600
AVG_128 = 0x0800
AVG_256 = 0x0A00
AVG_512 = 0x0C00
AVG_1024 = 0x0E00

# Bus voltage conversion time (bits 8:6)
VBUS_140US = 0x0000
VBUS_204US = 0x0040
VBUS_332US = 0x0080
VBUS_588US = 0x00C0
VBUS_1100US = 0x0100
VBUS_2116US = 0x0140
VBUS_4156US = 0x0180
VBUS_8244US = 0x01C0

# Shunt voltage conversion time (bits 5:3)
VSHUNT_140US = 0x0000
VSHUNT_204US = 0x0008
VSHUNT_332US = 0x0010
VSHUNT_588US = 0x0018
VSHUNT_1100US = 0x0020
VSHUNT_2116US = 0x0028
VSHUNT_4156US = 0x0030
VSHUNT_8244US = 0x0038

# Operating mode (bits 2:0)
MODE_SHUTDOWN = 0x0000
MODE_SHUNT_TRIG = 0x0001
MODE_BUS_TRIG = 0x0002
MODE_SHUNT_BUS_TRIG = 0x0003
MODE_SHUNT_CONT = 0x0005
MODE_BUS_CONT = 0x0006
MODE_SHUNT_BUS_CONT = 0x0007

# Reset bit
_CONFIG_RESET = 0x8000

# Fixed LSB values
_BUS_VOLTAGE_LSB = 1.25e-3  # 1.25 mV per bit
_SHUNT_VOLTAGE_LSB = 2.5e-6  # 2.5 uV per bit


class INA226:
    """INA226 high-side/low-side current/power monitor."""

    def __init__(self, i2c, addr=0x40, shunt_ohms=0.005, max_current=5.5):
        """Initialize INA226.

        Args:
            i2c: machine.I2C instance
            addr: I2C address (default 0x40)
            shunt_ohms: Shunt resistor value in ohms (default 0.005 for HW1.1+)
            max_current: Maximum expected current in amps (for calibration)
        """
        self._i2c = i2c
        self._addr = addr
        self._shunt_ohms = shunt_ohms
        self._buf = bytearray(2)

        # Calculate calibration values
        self._current_lsb = max_current / 32768  # max_current / 2^15
        self._power_lsb = self._current_lsb * 25
        self._cal = int(0.00512 / (shunt_ohms * self._current_lsb))

    def _read_reg(self, reg):
        """Read a 16-bit register (big-endian)."""
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf)
        return struct.unpack(">H", self._buf)[0]

    def _read_reg_signed(self, reg):
        """Read a signed 16-bit register (big-endian)."""
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf)
        return struct.unpack(">h", self._buf)[0]

    def _write_reg(self, reg, value):
        """Write a 16-bit register (big-endian)."""
        self._i2c.writeto_mem(self._addr, reg, struct.pack(">H", value & 0xFFFF))

    def init(self, config=None):
        """Configure the INA226 and write calibration register.

        Args:
            config: Configuration register value. Defaults to continuous shunt+bus
                    measurement with 16x averaging and 1.1ms conversion times.
        """
        if config is None:
            config = AVG_16 | VBUS_1100US | VSHUNT_1100US | MODE_SHUNT_BUS_CONT
        self._write_reg(_REG_CONFIG, config)
        self._write_reg(_REG_CALIBRATION, self._cal)

    def reset(self):
        """Software reset the INA226."""
        self._write_reg(_REG_CONFIG, _CONFIG_RESET)

    def bus_voltage(self):
        """Read bus voltage in volts."""
        raw = self._read_reg(_REG_BUS_VOLTAGE)
        return raw * _BUS_VOLTAGE_LSB

    def shunt_voltage(self):
        """Read shunt voltage in volts (signed)."""
        raw = self._read_reg_signed(_REG_SHUNT_VOLTAGE)
        return raw * _SHUNT_VOLTAGE_LSB

    def current(self):
        """Read current in amps (signed). Requires calibration register set."""
        raw = self._read_reg_signed(_REG_CURRENT)
        return raw * self._current_lsb

    def power(self):
        """Read power in watts. Requires calibration register set."""
        raw = self._read_reg(_REG_POWER)
        return raw * self._power_lsb

    def manufacturer_id(self):
        """Read manufacturer ID (should be 0x5449)."""
        return self._read_reg(_REG_MANUFACTURER_ID)

    def die_id(self):
        """Read die ID (should be 0x2260)."""
        return self._read_reg(_REG_DIE_ID)
