"""Settings persistence — JSON file on flash.

Stores user preferences (target voltage, current, menu position)
and loads them on boot with validation and defaults.
"""

import json

_DEFAULTS = {
    "target_voltage_mv": 5000,
    "target_current_ma": 3000,
    "menu_position": 0,
}


class Settings:
    """Persistent settings backed by a JSON file."""

    def __init__(self, path="/settings.json"):
        self._path = path
        self.target_voltage_mv = _DEFAULTS["target_voltage_mv"]
        self.target_current_ma = _DEFAULTS["target_current_ma"]
        self.menu_position = _DEFAULTS["menu_position"]

    def load(self):
        """Load settings from file. Returns True if loaded, False if defaults used."""
        try:
            with open(self._path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False

        # Validate and apply each field, keeping defaults for missing/invalid
        if isinstance(data.get("target_voltage_mv"), int):
            self.target_voltage_mv = data["target_voltage_mv"]
        if isinstance(data.get("target_current_ma"), int):
            self.target_current_ma = data["target_current_ma"]
        if isinstance(data.get("menu_position"), int):
            self.menu_position = data["menu_position"]
        return True

    def save(self):
        """Save current settings to file."""
        data = {
            "target_voltage_mv": self.target_voltage_mv,
            "target_current_ma": self.target_current_ma,
            "menu_position": self.menu_position,
        }
        with open(self._path, "w") as f:
            json.dump(data, f)

    def to_dict(self):
        """Return settings as a dictionary."""
        return {
            "target_voltage_mv": self.target_voltage_mv,
            "target_current_ma": self.target_current_ma,
            "menu_position": self.menu_position,
        }
