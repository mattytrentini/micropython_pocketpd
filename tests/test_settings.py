"""Tests for settings persistence."""

import json
import os
import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

from testutil import assert_eq, assert_false, assert_true

from app.settings import Settings

_TEST_PATH = "/tmp/test_settings.json"


def _cleanup():
    try:  # noqa: SIM105 — contextlib.suppress not available in MicroPython
        os.remove(_TEST_PATH)
    except OSError:
        pass


def test_defaults():
    _cleanup()
    s = Settings(_TEST_PATH)
    assert_eq(s.target_voltage_mv, 5000)
    assert_eq(s.target_current_ma, 3000)
    assert_eq(s.menu_position, 0)


def test_save_and_load():
    _cleanup()
    s = Settings(_TEST_PATH)
    s.target_voltage_mv = 12000
    s.target_current_ma = 2500
    s.menu_position = 3
    s.save()

    s2 = Settings(_TEST_PATH)
    result = s2.load()
    assert_true(result, "load should return True")
    assert_eq(s2.target_voltage_mv, 12000)
    assert_eq(s2.target_current_ma, 2500)
    assert_eq(s2.menu_position, 3)


def test_load_missing_file():
    _cleanup()
    s = Settings(_TEST_PATH)
    result = s.load()
    assert_false(result, "load should return False for missing file")
    assert_eq(s.target_voltage_mv, 5000, "should keep defaults")


def test_load_corrupt_json():
    _cleanup()
    with open(_TEST_PATH, "w") as f:
        f.write("not valid json{{{")
    s = Settings(_TEST_PATH)
    result = s.load()
    assert_false(result, "load should return False for corrupt JSON")
    assert_eq(s.target_voltage_mv, 5000)


def test_load_partial_data():
    _cleanup()
    with open(_TEST_PATH, "w") as f:
        json.dump({"target_voltage_mv": 9000}, f)
    s = Settings(_TEST_PATH)
    s.load()
    assert_eq(s.target_voltage_mv, 9000, "loaded field")
    assert_eq(s.target_current_ma, 3000, "default for missing field")
    assert_eq(s.menu_position, 0, "default for missing field")


def test_load_invalid_type():
    _cleanup()
    with open(_TEST_PATH, "w") as f:
        json.dump({"target_voltage_mv": "not_an_int", "target_current_ma": 2000}, f)
    s = Settings(_TEST_PATH)
    s.load()
    assert_eq(s.target_voltage_mv, 5000, "invalid type keeps default")
    assert_eq(s.target_current_ma, 2000, "valid field loaded")


def test_to_dict():
    s = Settings(_TEST_PATH)
    s.target_voltage_mv = 15000
    s.target_current_ma = 1000
    s.menu_position = 2
    d = s.to_dict()
    assert_eq(d["target_voltage_mv"], 15000)
    assert_eq(d["target_current_ma"], 1000)
    assert_eq(d["menu_position"], 2)


def test_overwrite_save():
    _cleanup()
    s = Settings(_TEST_PATH)
    s.target_voltage_mv = 5000
    s.save()

    s.target_voltage_mv = 20000
    s.save()

    s2 = Settings(_TEST_PATH)
    s2.load()
    assert_eq(s2.target_voltage_mv, 20000, "should have latest value")
