"""Simulated I2C devices for PocketPD simulation.

Provides AP33772 and INA226 mock devices that respond to I2C commands
with realistic behavior — PDO negotiation, voltage/current tracking, etc.
"""

import struct

import machine

import config


def create_sim_i2c():
    """Create a mock I2C bus with simulated PocketPD devices.

    Returns:
        (i2c, sim_ap33772, sim_ina226) tuple
    """
    i2c = machine.I2C(
        config.I2C_ID,
        sda=machine.Pin(config.I2C_SDA),
        scl=machine.Pin(config.I2C_SCL),
        freq=config.I2C_FREQ,
    )

    ap = SimAP33772(i2c)
    ina = SimINA226(i2c)

    return i2c, ap, ina


class SimAP33772:
    """Simulated AP33772 USB PD sink controller.

    Pre-loaded with a typical 65W charger's PDO data:
    - 5V/3A, 9V/3A, 15V/3A, 20V/3.25A (fixed)
    - 3.3-21V/5A (PPS)

    Responds to RDO writes by updating the requested voltage/current,
    which SimINA226 can read to simulate output tracking.
    """

    def __init__(self, i2c):
        self.dev = machine.I2CDevice(addr=config.ADDR_AP33772, i2c=i2c)
        self.requested_voltage_mv = 5000
        self.requested_current_ma = 3000

        # Build PDO data
        pdos = [
            self._fixed_pdo(5000, 3000),
            self._fixed_pdo(9000, 3000),
            self._fixed_pdo(15000, 3000),
            self._fixed_pdo(20000, 3250),
            self._pps_pdo(3300, 21000, 5000),
        ]

        pdo_data = b""
        for p in pdos:
            pdo_data += p

        # Pre-populate registers
        self.dev.register_values[0x00] = pdo_data       # CMD_SRCPDO
        self.dev.register_values[0x1C] = bytes([len(pdos)])  # CMD_PDONUM
        self.dev.register_values[0x1D] = bytes([0x03])   # CMD_STATUS (ready + success)
        self.dev.register_values[0x1E] = bytes([0])      # CMD_MASK
        self.dev.register_values[0x20] = bytes([63])     # CMD_VOLTAGE (5V = 63 * 80mV)
        self.dev.register_values[0x21] = bytes([0])      # CMD_CURRENT (0A)
        self.dev.register_values[0x22] = bytes([25])     # CMD_TEMP (25C)
        self.dev.register_values[0x30] = bytes(4)        # CMD_RDO

    @staticmethod
    def _fixed_pdo(voltage_mv, max_current_ma):
        dword = ((voltage_mv // 50) & 0x3FF) << 10
        dword |= (max_current_ma // 10) & 0x3FF
        return struct.pack("<I", dword)

    @staticmethod
    def _pps_pdo(min_voltage_mv, max_voltage_mv, max_current_ma):
        dword = 0b11 << 30
        dword |= ((max_voltage_mv // 100) & 0xFF) << 17
        dword |= ((min_voltage_mv // 100) & 0xFF) << 8
        dword |= (max_current_ma // 50) & 0x7F
        return struct.pack("<I", dword)

    def update(self):
        """Check if an RDO was written and update simulated state."""
        rdo_bytes = self.dev.register_values.get(0x30, bytes(4))
        if rdo_bytes == bytes(4):
            return  # Reset or no request

        dword = struct.unpack("<I", rdo_bytes)[0]
        pos = (dword >> 28) & 0x7

        if pos == 5:
            # PPS request
            voltage_mv = ((dword >> 9) & 0x7FF) * 20
            current_ma = (dword & 0x7F) * 50
            self.requested_voltage_mv = voltage_mv
            self.requested_current_ma = current_ma
        elif 1 <= pos <= 4:
            # Fixed PDO request — voltage is determined by the PDO
            fixed_voltages = [5000, 9000, 15000, 20000]
            self.requested_voltage_mv = fixed_voltages[pos - 1]

        # Update voltage reading register
        self.dev.register_values[0x20] = bytes([self.requested_voltage_mv // 80])


class SimINA226:
    """Simulated INA226 power monitor.

    Returns configurable voltage/current readings. Can be linked to
    SimAP33772 to track requested voltage automatically.
    """

    def __init__(self, i2c):
        self.dev = machine.I2CDevice(addr=config.ADDR_INA226, i2c=i2c)
        self._voltage_mv = 5000
        self._current_ma = 0
        self._output_on = False

        # Pre-populate registers with zeros
        for reg in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
            self.dev.register_values[reg] = bytes(2)

        # Manufacturer and die ID
        self.dev.register_values[0xFE] = struct.pack(">H", 0x5449)
        self.dev.register_values[0xFF] = struct.pack(">H", 0x2260)

        self._update_registers()

    def set_readings(self, voltage_mv, current_ma):
        """Set simulated voltage/current readings."""
        self._voltage_mv = voltage_mv
        self._current_ma = current_ma
        self._update_registers()

    def set_output(self, on):
        """Update simulated output state."""
        self._output_on = on
        self._update_registers()

    def track_ap33772(self, sim_ap):
        """Update readings to track AP33772's requested voltage.

        Call this periodically in the simulation loop.
        """
        self._voltage_mv = sim_ap.requested_voltage_mv
        if not self._output_on:
            self._current_ma = 0
        self._update_registers()

    def _update_registers(self):
        """Update I2C register values from simulated readings."""
        # Bus voltage: 1.25mV/LSB
        bus_raw = int(self._voltage_mv / 1.25)
        self.dev.register_values[0x02] = struct.pack(">H", bus_raw & 0xFFFF)

        # Current: needs calibration register value
        # With default calibration (5mΩ, 5.5A max): current_lsb = 5.5/32768
        current_lsb = 5.5 / 32768
        current_a = self._current_ma / 1000
        current_raw = int(current_a / current_lsb)
        self.dev.register_values[0x04] = struct.pack(">h", current_raw)

        # Shunt voltage: V_shunt = I * R_shunt, 2.5uV/LSB
        shunt_v = current_a * config.SHUNT_RESISTANCE
        shunt_raw = int(shunt_v / 2.5e-6)
        self.dev.register_values[0x01] = struct.pack(">h", shunt_raw)
