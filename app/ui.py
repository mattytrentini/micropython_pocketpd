"""UI rendering functions for each PocketPD screen.

Each draw_* function takes a Display instance and the relevant state data,
clears the display, renders the screen, and calls show().
"""

VERSION = "0.1.0"


def draw_boot(display):
    """Splash screen shown during startup."""
    display.clear()
    display.text_medium("PocketPD", 10, 20)
    display.text_small("MicroPython", 35, 30)
    display.text_small("v" + VERSION, 48, 45)
    display.show()


def draw_capabilities(display, fixed_pdos, pps_pdos):
    """Show available charger PDO/PPS profiles.

    Args:
        display: Display instance
        fixed_pdos: list of FixedPDO
        pps_pdos: list of PPSPDO
    """
    display.clear()
    display.text_small("Source Profiles", 0, 0)
    display.hline(0, 11, 128)

    row = 14
    for pdo in fixed_pdos:
        if row > 54:
            break
        v = pdo.voltage_mv / 1000
        a = pdo.max_current_ma / 1000
        display.text_small("%.1fV %.1fA" % (v, a), row, 2)
        row += 12

    for pdo in pps_pdos:
        if row > 54:
            break
        vmin = pdo.min_voltage_mv / 1000
        vmax = pdo.max_voltage_mv / 1000
        a = pdo.max_current_ma / 1000
        display.text_small("PPS %.0f-%.0fV %.1fA" % (vmin, vmax, a), row, 2)
        row += 12

    display.show()


def draw_normal(display, voltage_mv, current_ma, target_v_mv, target_i_ma,
                output_on, is_pps, cv_mode, adjust_voltage, cursor_pos, blink_on):
    """Main operating screen with voltage/current readout.

    Args:
        display: Display instance
        voltage_mv: Measured voltage in mV
        current_ma: Measured current in mA
        target_v_mv: Target voltage in mV (PPS mode)
        target_i_ma: Target current in mA (PPS mode)
        output_on: Whether output is enabled
        is_pps: Whether in PPS mode
        cv_mode: True for CV, False for CC
        adjust_voltage: True if encoder adjusts voltage, False for current
        cursor_pos: Adjustment digit position (0-2 for scale indicator)
        blink_on: Cursor blink state
    """
    display.clear()

    # Measured voltage (large)
    v = voltage_mv / 1000
    display.text_large("%.2fV" % v, 0, 0)

    # Measured current (medium, below voltage)
    a = current_ma / 1000
    display.text_medium("%.3fA" % a, 38, 0)

    # Right side indicators
    if output_on:
        display.fill_rect(108, 0, 20, 10, 1)
        display.text_small("ON", 1, 110)
    else:
        display.rect(108, 0, 20, 10, 1)
        display.text_small("OFF", 1, 105)

    # CV/CC indicator
    mode_str = "CV" if cv_mode else "CC"
    display.text_small(mode_str, 13, 112)

    # PPS target values (small, right side)
    if is_pps:
        tv = target_v_mv / 1000
        ti = target_i_ma / 1000
        display.text_small("%.1fV" % tv, 38, 85)
        display.text_small("%.1fA" % ti, 50, 85)

        # Adjustment indicator
        adj_char = "V" if adjust_voltage else "A"
        if blink_on:
            display.text_small(">" + adj_char, 56, 0)

    display.show()


def draw_energy(display, voltage_mv, current_ma, power_mw, elapsed_s, wh, ah):
    """Energy accumulation screen.

    Args:
        display: Display instance
        voltage_mv: Measured voltage in mV
        current_ma: Measured current in mA
        power_mw: Measured power in mW
        elapsed_s: Elapsed time in seconds
        wh: Accumulated watt-hours
        ah: Accumulated amp-hours
    """
    display.clear()

    v = voltage_mv / 1000
    a = current_ma / 1000
    w = power_mw / 1000

    # Top row: V and A compact
    display.text_small("%.2fV  %.3fA" % (v, a), 0, 0)
    display.hline(0, 11, 128)

    # Power
    display.text_medium("%.2fW" % w, 14, 0)

    # Elapsed time
    hours = elapsed_s // 3600
    mins = (elapsed_s % 3600) // 60
    secs = elapsed_s % 60
    display.text_small("%d:%02d:%02d" % (hours, mins, secs), 14, 80)

    # Energy
    display.hline(0, 36, 128)
    display.text_medium("%.3fWh" % wh, 39, 0)
    display.text_small("%.4fAh" % ah, 54, 0)

    display.show()


def draw_menu(display, profiles, selected_idx, is_pps_list):
    """Profile selection menu.

    Args:
        display: Display instance
        profiles: list of (label_str,) items to display
        selected_idx: Currently highlighted index
        is_pps_list: Whether we're showing PPS profiles
    """
    display.clear()

    title = "PPS Profiles" if is_pps_list else "Fixed Profiles"
    display.text_small(title, 0, 0)
    display.hline(0, 11, 128)

    row = 14
    max_visible = 4
    # Scroll window
    start = max(0, selected_idx - max_visible + 1)
    end = min(len(profiles), start + max_visible)

    for i in range(start, end):
        if i == selected_idx:
            display.fill_rect(0, row, 128, 12, 1)
            # Inverted text for selection — render directly with framebuf
            display.device.text(profiles[i], 4, row + 2, 0)
        else:
            display.text_small(profiles[i], row, 4)
        row += 12

    display.show()
