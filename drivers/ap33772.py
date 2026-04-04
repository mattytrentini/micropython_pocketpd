"""AP33772 USB PD 3.0 sink controller driver.

Communicates via I2C with the AP33772, which handles all USB PD protocol
negotiation internally. This driver sends high-level commands to request
specific voltages and currents.

Reference: AP33772 datasheet, CentyLab/PocketPD firmware, charkster/AP33772_I2C
"""

import struct

try:
    from time import sleep_ms  # type: ignore[attr-defined]  # MicroPython
except ImportError:
    from time import sleep

    def sleep_ms(ms):
        sleep(ms / 1000)

# Register addresses
_CMD_SRCPDO = 0x00  # Source PDO data (4 bytes per PDO), read
_CMD_PDONUM = 0x1C  # Number of PDOs available, read (1 byte)
_CMD_STATUS = 0x1D  # Device status register, read (1 byte)
_CMD_MASK = 0x1E  # Event/interrupt mask, read/write (1 byte)
_CMD_VOLTAGE = 0x20  # Measured voltage, read (1 byte, 80mV/LSB)
_CMD_CURRENT = 0x21  # Measured current, read (1 byte, 24mA/LSB)
_CMD_TEMP = 0x22  # Temperature, read (1 byte, 1C/LSB)
_CMD_OCPTHR = 0x23  # Over-current protection threshold, write
_CMD_OTPTHR = 0x24  # Over-temperature protection threshold, write
_CMD_DRTHR = 0x25  # Derating temperature threshold, write
_CMD_TR25 = 0x28  # NTC resistance at 25C, write (2 bytes)
_CMD_TR50 = 0x2A  # NTC resistance at 50C, write (2 bytes)
_CMD_TR75 = 0x2C  # NTC resistance at 75C, write (2 bytes)
_CMD_TR100 = 0x2E  # NTC resistance at 100C, write (2 bytes)
_CMD_RDO = 0x30  # Request Data Object, write (4 bytes)

# Status register bit masks
STATUS_READY = 0x01
STATUS_SUCCESS = 0x02
STATUS_NEW_PDO = 0x04
STATUS_OVP = 0x10
STATUS_OCP = 0x20
STATUS_OTP = 0x40
STATUS_DR = 0x80

# Measurement LSBs
_VOLTAGE_LSB_MV = 80  # mV per LSB
_CURRENT_LSB_MA = 24  # mA per LSB

# Maximum number of PDOs
_MAX_PDOS = 7


class FixedPDO:
    """A Fixed Power Data Object from a USB PD source."""

    __slots__ = ("voltage_mv", "max_current_ma", "index")

    def __init__(self, voltage_mv, max_current_ma, index):
        self.voltage_mv = voltage_mv
        self.max_current_ma = max_current_ma
        self.index = index  # 1-based PDO position

    def __repr__(self):
        return "FixedPDO(%dmV, %dmA, idx=%d)" % (
            self.voltage_mv,
            self.max_current_ma,
            self.index,
        )


class PPSPDO:
    """A Programmable Power Supply PDO from a USB PD source."""

    __slots__ = ("min_voltage_mv", "max_voltage_mv", "max_current_ma", "index")

    def __init__(self, min_voltage_mv, max_voltage_mv, max_current_ma, index):
        self.min_voltage_mv = min_voltage_mv
        self.max_voltage_mv = max_voltage_mv
        self.max_current_ma = max_current_ma
        self.index = index  # 1-based PDO position

    def __repr__(self):
        return "PPSPDO(%d-%dmV, %dmA, idx=%d)" % (
            self.min_voltage_mv,
            self.max_voltage_mv,
            self.max_current_ma,
            self.index,
        )


def parse_pdo(raw_bytes, index):
    """Parse a 4-byte PDO into a FixedPDO or PPSPDO.

    Args:
        raw_bytes: 4 bytes of PDO data (little-endian from AP33772)
        index: 1-based PDO position

    Returns:
        FixedPDO, PPSPDO, or None if unrecognized type
    """
    dword = struct.unpack("<I", raw_bytes)[0]
    pdo_type = (dword >> 30) & 0x03

    if pdo_type == 0b00:
        # Fixed PDO
        voltage_mv = ((dword >> 10) & 0x3FF) * 50
        max_current_ma = (dword & 0x3FF) * 10
        return FixedPDO(voltage_mv, max_current_ma, index)
    elif pdo_type == 0b11:
        # PPS (Augmented PDO)
        max_voltage_mv = ((dword >> 17) & 0xFF) * 100
        min_voltage_mv = ((dword >> 8) & 0xFF) * 100
        max_current_ma = (dword & 0x7F) * 50
        return PPSPDO(min_voltage_mv, max_voltage_mv, max_current_ma, index)

    return None


def build_fixed_rdo(pdo_index, operating_current_ma, max_current_ma):
    """Build a 4-byte RDO for a Fixed PDO request.

    Args:
        pdo_index: 1-based PDO position
        operating_current_ma: Operating current in mA
        max_current_ma: Maximum current in mA

    Returns:
        4 bytes (little-endian) to write to CMD_RDO
    """
    rdo = (pdo_index & 0x7) << 28
    rdo |= (int(operating_current_ma / 10) & 0x3FF) << 10
    rdo |= int(max_current_ma / 10) & 0x3FF
    return struct.pack("<I", rdo)


def build_pps_rdo(pdo_index, voltage_mv, current_ma):
    """Build a 4-byte RDO for a PPS request.

    Args:
        pdo_index: 1-based PDO position
        voltage_mv: Requested voltage in mV (20mV resolution)
        current_ma: Requested current in mA (50mA resolution)

    Returns:
        4 bytes (little-endian) to write to CMD_RDO
    """
    rdo = (pdo_index & 0x7) << 28
    rdo |= (int(voltage_mv / 20) & 0x7FF) << 9
    rdo |= int(current_ma / 50) & 0x7F
    return struct.pack("<I", rdo)


class AP33772:
    """AP33772 USB PD 3.0 sink controller."""

    def __init__(self, i2c, addr=0x51):
        self._i2c = i2c
        self._addr = addr
        self.fixed_pdos = []
        self.pps_pdos = []

    def _read_reg(self, reg, length):
        """Read length bytes from register."""
        return self._i2c.readfrom_mem(self._addr, reg, length)

    def _write_reg(self, reg, data):
        """Write bytes to register."""
        self._i2c.writeto_mem(self._addr, reg, data)

    def read_status(self):
        """Read status register. Returns raw status byte."""
        return self._read_reg(_CMD_STATUS, 1)[0]

    def is_ready(self):
        """Check if PD negotiation is complete."""
        return bool(self.read_status() & STATUS_READY)

    def has_new_pdo(self):
        """Check if new PDOs are available."""
        return bool(self.read_status() & STATUS_NEW_PDO)

    def check_protection(self):
        """Check for protection flags. Returns dict of active protections."""
        status = self.read_status()
        return {
            "ovp": bool(status & STATUS_OVP),
            "ocp": bool(status & STATUS_OCP),
            "otp": bool(status & STATUS_OTP),
            "derating": bool(status & STATUS_DR),
        }

    def read_pdo_count(self):
        """Read the number of available PDOs."""
        return self._read_reg(_CMD_PDONUM, 1)[0]

    def read_pdos(self):
        """Read and parse all available PDOs from the source.

        Updates self.fixed_pdos and self.pps_pdos lists.
        Returns tuple of (fixed_pdos, pps_pdos).
        """
        count = self.read_pdo_count()
        if count > _MAX_PDOS:
            count = _MAX_PDOS

        raw = self._read_reg(_CMD_SRCPDO, count * 4)

        self.fixed_pdos = []
        self.pps_pdos = []

        for i in range(count):
            pdo_bytes = raw[i * 4 : (i + 1) * 4]
            pdo = parse_pdo(pdo_bytes, i + 1)  # 1-based index
            if isinstance(pdo, FixedPDO):
                self.fixed_pdos.append(pdo)
            elif isinstance(pdo, PPSPDO):
                self.pps_pdos.append(pdo)

        return self.fixed_pdos, self.pps_pdos

    @property
    def has_pps(self):
        """Whether the source supports PPS."""
        return len(self.pps_pdos) > 0

    def read_voltage_mv(self):
        """Read measured bus voltage in millivolts."""
        raw = self._read_reg(_CMD_VOLTAGE, 1)[0]
        return raw * _VOLTAGE_LSB_MV

    def read_current_ma(self):
        """Read measured current in milliamps."""
        raw = self._read_reg(_CMD_CURRENT, 1)[0]
        return raw * _CURRENT_LSB_MA

    def read_temperature(self):
        """Read temperature in degrees Celsius."""
        return self._read_reg(_CMD_TEMP, 1)[0]

    def request_fixed_pdo(self, pdo):
        """Request a specific fixed PDO.

        Args:
            pdo: FixedPDO instance to request
        """
        rdo = build_fixed_rdo(pdo.index, pdo.max_current_ma, pdo.max_current_ma)
        self._write_reg(_CMD_RDO, rdo)

    def request_pps(self, pdo, voltage_mv, current_ma):
        """Request a PPS voltage/current.

        Args:
            pdo: PPSPDO instance to use
            voltage_mv: Requested voltage in mV (clamped to PPS range, 20mV steps)
            current_ma: Requested current in mA (clamped to PPS max, 50mA steps)

        Returns:
            Tuple of (actual_voltage_mv, actual_current_ma) after clamping/rounding
        """
        # Clamp to PPS range
        voltage_mv = max(pdo.min_voltage_mv, min(pdo.max_voltage_mv, voltage_mv))
        current_ma = min(pdo.max_current_ma, current_ma)

        # Round to step sizes
        voltage_mv = (voltage_mv // 20) * 20
        current_ma = (current_ma // 50) * 50

        rdo = build_pps_rdo(pdo.index, voltage_mv, current_ma)
        self._write_reg(_CMD_RDO, rdo)
        return voltage_mv, current_ma

    def select_voltage(self, target_mv):
        """Smart voltage selection — picks best PDO/PPS for the target voltage.

        Strategy:
        1. If PPS covers the target voltage, use PPS (fine-grained control)
        2. Otherwise, find the closest fixed PDO at or below target
        3. If PPS max voltage exceeds best fixed PDO, prefer PPS at max

        Args:
            target_mv: Desired voltage in millivolts

        Returns:
            Tuple of (pdo, voltage_mv) where pdo is a FixedPDO or PPSPDO,
            or (None, 0) if no suitable PDO found
        """
        # Check PPS range first
        for pps in self.pps_pdos:
            if pps.min_voltage_mv <= target_mv <= pps.max_voltage_mv:
                return pps, (target_mv // 20) * 20

        # Find closest fixed PDO at or below target
        best_fixed = None
        best_voltage = 0
        for fixed in self.fixed_pdos:
            if fixed.voltage_mv <= target_mv and fixed.voltage_mv > best_voltage:
                best_fixed = fixed
                best_voltage = fixed.voltage_mv

        # Check if any PPS max exceeds best fixed
        for pps in self.pps_pdos:
            pps_best = min(pps.max_voltage_mv, target_mv)
            pps_best = (pps_best // 20) * 20
            if pps_best > best_voltage:
                return pps, pps_best

        if best_fixed:
            return best_fixed, best_voltage

        return None, 0

    def reset(self):
        """Send a hard reset (all-zero RDO). Causes temporary power loss."""
        self._write_reg(_CMD_RDO, bytes(4))

    def set_ntc_resistance(self, r25, r50, r75, r100):
        """Set NTC thermistor resistance values for temperature calibration.

        Args:
            r25: Resistance at 25C in ohms (16-bit)
            r50: Resistance at 50C in ohms (16-bit)
            r75: Resistance at 75C in ohms (16-bit)
            r100: Resistance at 100C in ohms (16-bit)
        """
        for reg, val in (
            (_CMD_TR25, r25),
            (_CMD_TR50, r50),
            (_CMD_TR75, r75),
            (_CMD_TR100, r100),
        ):
            self._write_reg(reg, struct.pack("<H", val))
            sleep_ms(5)  # Required delay between NTC writes
