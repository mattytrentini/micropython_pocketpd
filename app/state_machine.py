"""PocketPD state machine — coordinates drivers, UI, and user input.

Six states: BOOT → OBTAIN → CAPDISPLAY → NORMAL_PPS/NORMAL_PDO, plus MENU.
Designed to run as cooperative async tasks.
"""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import config


async def _sleep_ms(ms):
    """asyncio.sleep_ms on MicroPython, asyncio.sleep(s) on CPython."""
    try:
        await asyncio.sleep_ms(ms)  # type: ignore[attr-defined]
    except AttributeError:
        await asyncio.sleep(ms / 1000)
from app import ui
from app.energy import EnergyTracker
from drivers.button import EVENT_LONG, EVENT_SHORT

# States
STATE_BOOT = 0
STATE_OBTAIN = 1
STATE_CAPDISPLAY = 2
STATE_NORMAL_PPS = 3
STATE_NORMAL_PDO = 4
STATE_MENU = 5

# Voltage increment scales (mV)
V_SCALES = (20, 100, 1000)
# Current increment scales (mA)
I_SCALES = (50, 100, 1000)


class StateMachine:
    """Main application state machine."""

    def __init__(self, display, ap33772, ina226, btn_output, btn_select, btn_encoder,
                 encoder, output_pin, settings, _ticks_ms=None, _ticks_diff=None):
        self.display = display
        self.pd = ap33772
        self.ina = ina226
        self.btn_output = btn_output
        self.btn_select = btn_select
        self.btn_encoder = btn_encoder
        self.encoder = encoder
        self.output_pin = output_pin
        self.settings = settings

        self.energy = EnergyTracker(_ticks_ms=_ticks_ms, _ticks_diff=_ticks_diff)

        # State
        self.state = STATE_BOOT
        self._state_start_ms = 0

        # Operating state
        self.output_on = False
        self.adjust_voltage = True  # True=voltage, False=current
        self.v_scale_idx = 1  # Index into V_SCALES (default 100mV)
        self.i_scale_idx = 1  # Index into I_SCALES (default 100mA)
        self.display_energy = False  # Normal vs energy display mode
        self.blink_on = True
        self.cv_mode = True

        # Measurements
        self.voltage_mv = 0
        self.current_ma = 0

        # Menu
        self._menu_profiles = []
        self._menu_is_pps = False

    def _set_state(self, new_state):
        self.state = new_state

    # --- Sensor reading ---

    def read_sensors(self):
        """Read INA226 measurements."""
        self.voltage_mv = int(self.ina.bus_voltage() * 1000)
        self.current_ma = int(self.ina.current() * 1000)
        if self.current_ma < 0:
            self.current_ma = 0

    # --- Output control ---

    def set_output(self, on):
        """Enable or disable power output."""
        self.output_on = on
        self.output_pin.value(1 if on else 0)
        if on:
            self.energy.start()
        else:
            self.energy.stop()

    def toggle_output(self):
        self.set_output(not self.output_on)

    # --- CV/CC detection ---

    def detect_cv_cc(self):
        """Detect constant voltage vs constant current mode."""
        if self.state != STATE_NORMAL_PPS or not self.output_on:
            self.cv_mode = True
            return
        target_v = self.settings.target_voltage_mv
        target_i = self.settings.target_current_ma
        # CC when: measured V < target V and measured I is near target I
        if (self.voltage_mv < target_v - 200
                and abs(self.current_ma - target_i) < 150):
            self.cv_mode = False
        else:
            self.cv_mode = True

    # --- State handlers ---

    def handle_boot(self):
        ui.draw_boot(self.display)

    def handle_obtain(self):
        """Read PDOs from charger."""
        self.pd.read_pdos()

    def handle_capdisplay(self):
        ui.draw_capabilities(self.display, self.pd.fixed_pdos, self.pd.pps_pdos)

    def _enter_normal(self):
        """Transition to the appropriate normal state."""
        # Restore saved settings
        if self.pd.has_pps:
            self._set_state(STATE_NORMAL_PPS)
        else:
            self._set_state(STATE_NORMAL_PDO)

    def handle_normal(self):
        """Handle normal operating state (PPS or PDO)."""
        self.read_sensors()
        self.detect_cv_cc()

        if self.output_on:
            self.energy.update(self.voltage_mv, self.current_ma)

        if self.display_energy:
            power_mw = self.voltage_mv * self.current_ma // 1000
            ui.draw_energy(
                self.display, self.voltage_mv, self.current_ma,
                power_mw, int(self.energy.elapsed_s),
                self.energy.wh, self.energy.ah,
            )
        else:
            ui.draw_normal(
                self.display, self.voltage_mv, self.current_ma,
                self.settings.target_voltage_mv, self.settings.target_current_ma,
                self.output_on, self.state == STATE_NORMAL_PPS, self.cv_mode,
                self.adjust_voltage, self.v_scale_idx if self.adjust_voltage else self.i_scale_idx,
                self.blink_on,
            )

    def handle_menu(self):
        """Render the menu screen."""
        ui.draw_menu(
            self.display, self._menu_profiles,
            self.settings.menu_position, self._menu_is_pps,
        )

    def _build_menu(self):
        """Build profile list for menu."""
        self._menu_profiles = []
        if self.pd.has_pps:
            self._menu_is_pps = True
            for pdo in self.pd.pps_pdos:
                self._menu_profiles.append(
                    "PPS %.1f-%.1fV" % (pdo.min_voltage_mv / 1000, pdo.max_voltage_mv / 1000)
                )
        for pdo in self.pd.fixed_pdos:
            self._menu_profiles.append(
                "%.1fV %.1fA" % (pdo.voltage_mv / 1000, pdo.max_current_ma / 1000)
            )

    # --- Input handling ---

    def process_inputs(self):
        """Poll all buttons and encoder, dispatch events based on current state."""
        out_ev = self.btn_output.update()
        sel_ev = self.btn_select.update()
        enc_ev = self.btn_encoder.update()
        enc_delta = self.encoder.update()

        if self.state in (STATE_NORMAL_PPS, STATE_NORMAL_PDO):
            self._handle_normal_inputs(out_ev, sel_ev, enc_ev, enc_delta)
        elif self.state == STATE_MENU:
            self._handle_menu_inputs(sel_ev, enc_delta)
        elif self.state == STATE_CAPDISPLAY and (out_ev or sel_ev or enc_ev):
            self._enter_normal()

    def _handle_normal_inputs(self, out_ev, sel_ev, enc_ev, enc_delta):
        # Output button
        if out_ev == EVENT_SHORT:
            self.toggle_output()
        elif out_ev == EVENT_LONG:
            self.display_energy = not self.display_energy

        # Select V/I button
        if sel_ev == EVENT_SHORT:
            self.adjust_voltage = not self.adjust_voltage

        # Encoder button
        if enc_ev == EVENT_SHORT:
            # Cycle increment scale
            if self.adjust_voltage:
                self.v_scale_idx = (self.v_scale_idx + 1) % len(V_SCALES)
            else:
                self.i_scale_idx = (self.i_scale_idx + 1) % len(I_SCALES)
        elif enc_ev == EVENT_LONG:
            # Enter menu
            self._build_menu()
            self.settings.menu_position = 0
            self._set_state(STATE_MENU)
            return

        # Encoder rotation (PPS only)
        if enc_delta != 0 and self.state == STATE_NORMAL_PPS:
            if self.adjust_voltage:
                step = V_SCALES[self.v_scale_idx] * enc_delta
                self.settings.target_voltage_mv += step
            else:
                step = I_SCALES[self.i_scale_idx] * enc_delta
                self.settings.target_current_ma += step

            # Clamp and send to AP33772
            if self.pd.pps_pdos:
                pps = self.pd.pps_pdos[0]
                self.settings.target_voltage_mv = max(
                    pps.min_voltage_mv,
                    min(pps.max_voltage_mv, self.settings.target_voltage_mv),
                )
                self.settings.target_current_ma = max(
                    0, min(pps.max_current_ma, self.settings.target_current_ma)
                )
                self.pd.request_pps(
                    pps,
                    self.settings.target_voltage_mv,
                    self.settings.target_current_ma,
                )

    def _handle_menu_inputs(self, sel_ev, enc_delta):
        if enc_delta != 0:
            n = len(self._menu_profiles)
            if n > 0:
                self.settings.menu_position = (self.settings.menu_position + enc_delta) % n

        if sel_ev == EVENT_LONG:
            # Select profile and return to normal
            self._apply_menu_selection()
            self._enter_normal()

    def _apply_menu_selection(self):
        """Apply the selected menu profile."""
        idx = self.settings.menu_position
        # Count PPS profiles first
        n_pps = len(self.pd.pps_pdos)
        if idx < n_pps:
            pps = self.pd.pps_pdos[idx]
            self.pd.request_pps(
                pps,
                self.settings.target_voltage_mv,
                self.settings.target_current_ma,
            )
        else:
            fixed_idx = idx - n_pps
            if fixed_idx < len(self.pd.fixed_pdos):
                self.pd.request_fixed_pdo(self.pd.fixed_pdos[fixed_idx])

    # --- Async tasks ---

    async def run(self):
        """Main application loop — runs the three cooperative tasks."""
        # Boot
        self.handle_boot()
        await _sleep_ms(500)

        # Obtain PDOs
        self._set_state(STATE_OBTAIN)
        self.handle_obtain()
        await _sleep_ms(500)

        # Show capabilities
        self._set_state(STATE_CAPDISPLAY)
        self.handle_capdisplay()
        await _sleep_ms(3000)

        # Enter normal mode if not already transitioned by button
        if self.state == STATE_CAPDISPLAY:
            self._enter_normal()

        # Load saved settings
        self.settings.load()

        # Start concurrent tasks
        await asyncio.gather(
            self._sensor_loop(),
            self._blink_loop(),
            self._save_loop(),
        )

    async def _sensor_loop(self):
        """~33ms loop: read sensors, process inputs, update display."""
        while True:
            self.process_inputs()
            if self.state in (STATE_NORMAL_PPS, STATE_NORMAL_PDO):
                self.handle_normal()
            elif self.state == STATE_MENU:
                self.handle_menu()
            await _sleep_ms(config.SENSOR_LOOP_MS)

    async def _blink_loop(self):
        """~500ms loop: toggle cursor blink state."""
        while True:
            self.blink_on = not self.blink_on
            await _sleep_ms(config.BLINK_LOOP_MS)

    async def _save_loop(self):
        """~2s loop: persist settings to flash."""
        while True:
            await _sleep_ms(config.SAVE_LOOP_MS)
            self.settings.save()
