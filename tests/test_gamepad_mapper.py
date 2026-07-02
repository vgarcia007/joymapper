"""
Tests for gamepad_mapper.py - Verifies non-blocking button handling.

Each mapping mode is tested in isolation and in combination to ensure that:
  - Button state is tracked independently per button.
  - No handler blocks the event loop.
  - Held buttons do not prevent other buttons from being processed.
  - Short/long press logic stores the timestamp on button-down and evaluates on button-up.
  - Toggle state is per-button and does not affect other buttons.
"""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Stub out pygame and keyboard before importing the module under test so that
# the tests can run on any platform without actual hardware or system hooks.
# ---------------------------------------------------------------------------

_pygame_stub = types.ModuleType("pygame")
_pygame_stub.init = lambda: None
_pygame_stub.joystick = MagicMock()
_pygame_stub.time = MagicMock()
_pygame_stub.event = MagicMock()
_pygame_stub.JOYBUTTONDOWN = 1
_pygame_stub.JOYBUTTONUP = 2
_pygame_stub.JOYAXISMOTION = 3
_pygame_stub.JOYHATMOTION = 4
_pygame_stub.NOFRAME = 0x00000020
_pygame_stub.HIDDEN = 0x00000040
_pygame_display_stub = MagicMock()
_pygame_display_stub.get_surface.return_value = None  # no surface yet
_pygame_stub.display = _pygame_display_stub
sys.modules.setdefault("pygame", _pygame_stub)
sys.modules.setdefault("keyboard", MagicMock())

import gamepad_mapper  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mapper(mappings: dict) -> gamepad_mapper.GamepadMapper:
    """Create a GamepadMapper with the given mappings and a mock joystick."""
    joystick = MagicMock()
    config = {"poll_interval_ms": 5, "mappings": mappings}
    return gamepad_mapper.GamepadMapper(joystick, config)


# ---------------------------------------------------------------------------
# press_release mode
# ---------------------------------------------------------------------------

class TestPressReleaseMode(unittest.TestCase):
    def setUp(self):
        self.mapper = _make_mapper({
            "0": {"mode": "press_release", "on_press": "a", "on_release": "b"},
        })

    def test_button_down_sends_on_press(self):
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_down(0)
            mock_send.assert_called_once_with("a")

    def test_button_up_sends_on_release(self):
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_up(0)
            self.assertEqual(mock_send.call_args_list, [call("a"), call("b")])

    def test_duplicate_button_down_ignored(self):
        """A second JOYBUTTONDOWN for the same button must not re-send on_press."""
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_down(0)  # duplicate – must be ignored
            mock_send.assert_called_once_with("a")

    def test_button_up_without_prior_down_is_ignored(self):
        """A JOYBUTTONUP with no matching JOYBUTTONDOWN must not fire on_release."""
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_up(0)  # no prior down
            mock_send.assert_not_called()

    def test_two_buttons_are_independent(self):
        """Holding button 0 must not prevent button 1 from being processed."""
        mapper = _make_mapper({
            "0": {"mode": "press_release", "on_press": "a", "on_release": "b"},
            "1": {"mode": "press_release", "on_press": "c", "on_release": "d"},
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            mapper._handle_button_down(0)
            mapper._handle_button_down(1)  # button 1 pressed while button 0 held
            mapper._handle_button_up(0)
            mapper._handle_button_up(1)
            self.assertEqual(
                mock_send.call_args_list,
                [call("a"), call("c"), call("b"), call("d")],
            )


# ---------------------------------------------------------------------------
# toggle mode
# ---------------------------------------------------------------------------

class TestToggleMode(unittest.TestCase):
    def setUp(self):
        self.mapper = _make_mapper({
            "0": {"mode": "toggle", "sequence": ["a", "b", "c"]},
        })

    def test_cycles_through_sequence(self):
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_up(0)
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_up(0)
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_up(0)
            # After the full cycle, wraps back to the beginning
            self.mapper._handle_button_down(0)
            self.assertEqual(
                mock_send.call_args_list,
                [call("a"), call("b"), call("c"), call("a")],
            )

    def test_two_toggle_buttons_have_independent_indices(self):
        mapper = _make_mapper({
            "0": {"mode": "toggle", "sequence": ["a", "b"]},
            "1": {"mode": "toggle", "sequence": ["x", "y"]},
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            mapper._handle_button_down(0)  # a
            mapper._handle_button_up(0)
            mapper._handle_button_down(1)  # x
            mapper._handle_button_up(1)
            mapper._handle_button_down(0)  # b  (button 1 did not advance button 0's index)
            mapper._handle_button_up(0)
            mapper._handle_button_down(1)  # y
            self.assertEqual(
                mock_send.call_args_list,
                [call("a"), call("x"), call("b"), call("y")],
            )


# ---------------------------------------------------------------------------
# press mode
# ---------------------------------------------------------------------------

class TestPressMode(unittest.TestCase):
    def setUp(self):
        self.mapper = _make_mapper({
            "0": {"mode": "press", "key": "enter"},
        })

    def test_button_down_sends_key(self):
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_down(0)
            mock_send.assert_called_once_with("enter")

    def test_button_up_sends_nothing(self):
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_up(0)
            mock_send.assert_called_once_with("enter")  # only the down event


# ---------------------------------------------------------------------------
# hold mode
# ---------------------------------------------------------------------------

class TestHoldMode(unittest.TestCase):
    def setUp(self):
        self.mapper = _make_mapper({
            "0": {"mode": "hold", "key": "shift"},
        })

    def test_button_down_holds_key(self):
        with patch.object(gamepad_mapper, "key_down") as mock_down:
            self.mapper._handle_button_down(0)
            mock_down.assert_called_once_with("shift")
        self.assertIn(0, self.mapper._held_keys)

    def test_button_up_releases_key(self):
        with patch.object(gamepad_mapper, "key_down"), \
             patch.object(gamepad_mapper, "key_up") as mock_up:
            self.mapper._handle_button_down(0)
            self.mapper._handle_button_up(0)
            mock_up.assert_called_once_with("shift")
        self.assertNotIn(0, self.mapper._held_keys)

    def test_two_hold_buttons_are_independent(self):
        mapper = _make_mapper({
            "0": {"mode": "hold", "key": "shift"},
            "1": {"mode": "hold", "key": "ctrl"},
        })
        with patch.object(gamepad_mapper, "key_down"), \
             patch.object(gamepad_mapper, "key_up") as mock_up:
            mapper._handle_button_down(0)
            mapper._handle_button_down(1)
            self.assertIn(0, mapper._held_keys)
            self.assertIn(1, mapper._held_keys)
            mapper._handle_button_up(0)
            mock_up.assert_called_once_with("shift")
            self.assertNotIn(0, mapper._held_keys)
            self.assertIn(1, mapper._held_keys)  # button 1 still held
            mapper._handle_button_up(1)
            self.assertNotIn(1, mapper._held_keys)


# ---------------------------------------------------------------------------
# short_long_press mode
# ---------------------------------------------------------------------------

class TestShortLongPressMode(unittest.TestCase):
    def _make_mapper(self):
        return _make_mapper({
            "0": {
                "mode": "short_long_press",
                "short_press": "f",
                "long_press": "g",
                "threshold_ms": 500,
            },
        })

    def test_button_down_records_timestamp_non_blocking(self):
        """_handle_button_down must return immediately after recording the timestamp."""
        mapper = self._make_mapper()
        # If it blocked, this call would never return.
        mapper._handle_button_down(0)
        self.assertIn(0, mapper._press_times)

    def test_short_press_fires_short_key(self):
        mapper = self._make_mapper()
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.3]  # 300 ms elapsed
            mapper._handle_button_down(0)
            mapper._handle_button_up(0)
            mock_send.assert_called_once_with("f")

    def test_long_press_fires_long_key(self):
        mapper = self._make_mapper()
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.6]  # 600 ms elapsed
            mapper._handle_button_down(0)
            mapper._handle_button_up(0)
            mock_send.assert_called_once_with("g")

    def test_exactly_at_threshold_fires_long_key(self):
        mapper = self._make_mapper()
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.5]  # exactly 500 ms
            mapper._handle_button_down(0)
            mapper._handle_button_up(0)
            mock_send.assert_called_once_with("g")

    def test_default_threshold_500ms(self):
        """When threshold_ms is omitted, defaults to 500 ms."""
        mapper = _make_mapper({
            "0": {"mode": "short_long_press", "short_press": "f", "long_press": "g"},
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.499]  # just under default
            mapper._handle_button_down(0)
            mapper._handle_button_up(0)
            mock_send.assert_called_once_with("f")

    def test_on_release_sent_after_short_key(self):
        """Optional on_release key is sent after the short-press key."""
        mapper = _make_mapper({
            "0": {
                "mode": "short_long_press",
                "short_press": "f",
                "long_press": "g",
                "on_release": "h",
                "threshold_ms": 500,
            },
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.3]  # short press
            mapper._handle_button_down(0)
            mapper._handle_button_up(0)
            self.assertEqual(mock_send.call_args_list, [call("f"), call("h")])

    def test_on_release_sent_after_long_key(self):
        """Optional on_release key is sent after the long-press key."""
        mapper = _make_mapper({
            "0": {
                "mode": "short_long_press",
                "short_press": "f",
                "long_press": "g",
                "on_release": "h",
                "threshold_ms": 500,
            },
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.7]  # long press
            mapper._handle_button_down(0)
            mapper._handle_button_up(0)
            self.assertEqual(mock_send.call_args_list, [call("g"), call("h")])

    def test_two_short_long_press_buttons_have_independent_timestamps(self):
        """Pressing two short_long_press buttons does not mix their timestamps."""
        mapper = _make_mapper({
            "0": {
                "mode": "short_long_press",
                "short_press": "f",
                "long_press": "g",
                "threshold_ms": 500,
            },
            "1": {
                "mode": "short_long_press",
                "short_press": "h",
                "long_press": "i",
                "threshold_ms": 500,
            },
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            # button 0 down at t=0.0, button 1 down at t=0.1
            # button 0 up at t=0.7  → 700 ms → long → "g"
            # button 1 up at t=0.4  → 300 ms → short → "h"
            mock_time.monotonic.side_effect = [0.0, 0.1, 0.7, 0.4]
            mapper._handle_button_down(0)
            mapper._handle_button_down(1)
            mapper._handle_button_up(0)
            mapper._handle_button_up(1)
            self.assertEqual(mock_send.call_args_list, [call("g"), call("h")])


# ---------------------------------------------------------------------------
# press_hold_release mode
# ---------------------------------------------------------------------------

class TestPressHoldReleaseMode(unittest.TestCase):
    def _make_mapper(self):
        return _make_mapper({
            "0": {
                "mode": "press_hold_release",
                "on_press": "a",
                "on_hold": "b",
                "on_release": "c",
                "threshold_ms": 500,
            },
        })

    def test_on_press_fires_immediately(self):
        mapper = self._make_mapper()
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mapper._handle_button_down(0)
            mock_send.assert_called_once_with("a")

    def test_on_hold_fires_after_threshold_while_held(self):
        mapper = self._make_mapper()
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mapper._handle_button_down(0)          # a
            mock_time.monotonic.return_value = 0.3
            mapper._process_hold_thresholds()      # below threshold: nothing
            mock_time.monotonic.return_value = 0.6
            mapper._process_hold_thresholds()      # b
            mock_time.monotonic.return_value = 0.9
            mapper._process_hold_thresholds()      # must not fire again
            mock_time.monotonic.return_value = 1.0
            mapper._handle_button_up(0)            # c
            self.assertEqual(
                mock_send.call_args_list,
                [call("a"), call("b"), call("c")],
            )

    def test_release_before_threshold_skips_on_hold(self):
        mapper = self._make_mapper()
        with patch.object(gamepad_mapper, "send_key") as mock_send, \
             patch("gamepad_mapper.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mapper._handle_button_down(0)          # a
            mock_time.monotonic.return_value = 0.2
            mapper._handle_button_up(0)            # c (no b)
            mock_time.monotonic.return_value = 0.8
            mapper._process_hold_thresholds()      # deadline cancelled: nothing
            self.assertEqual(mock_send.call_args_list, [call("a"), call("c")])


# ---------------------------------------------------------------------------
# Non-blocking / cross-button interaction
# ---------------------------------------------------------------------------

class TestNonBlockingBehavior(unittest.TestCase):
    def test_button_down_does_not_block(self):
        """_handle_button_down must return without waiting for button-up."""
        mapper = _make_mapper({
            "0": {"mode": "press_release", "on_press": "a", "on_release": "b"},
        })
        with patch.object(gamepad_mapper, "send_key"):
            # This would hang if the handler waited for button-up.
            mapper._handle_button_down(0)
        # If we reach here, the handler returned immediately.

    def test_held_button_does_not_block_other_buttons(self):
        """While button 0 is held, button 1 must be processed normally."""
        mapper = _make_mapper({
            "0": {"mode": "hold", "key": "shift"},
            "1": {"mode": "press", "key": "enter"},
        })
        with patch.object(gamepad_mapper, "key_down"), \
             patch.object(gamepad_mapper, "send_key") as mock_send:
            mapper._handle_button_down(0)   # hold shift
            mapper._handle_button_down(1)   # press enter while shift is held
            mapper._handle_button_up(1)     # release button 1
            mock_send.assert_called_once_with("enter")
            self.assertIn(0, mapper._pressed_buttons)    # button 0 still held
            self.assertNotIn(1, mapper._pressed_buttons) # button 1 released

    def test_press_release_and_press_together(self):
        """Press-release and press modes must not interfere with each other."""
        mapper = _make_mapper({
            "0": {"mode": "press_release", "on_press": "a", "on_release": "b"},
            "1": {"mode": "press", "key": "c"},
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            mapper._handle_button_down(0)
            mapper._handle_button_down(1)   # pressed while 0 is held
            mapper._handle_button_up(1)
            mapper._handle_button_up(0)
            self.assertEqual(
                mock_send.call_args_list,
                [call("a"), call("c"), call("b")],
            )

    def test_unmapped_button_does_not_affect_state(self):
        """Events for unmapped buttons must not corrupt state for mapped buttons."""
        mapper = _make_mapper({
            "0": {"mode": "press_release", "on_press": "a", "on_release": "b"},
        })
        with patch.object(gamepad_mapper, "send_key") as mock_send:
            mapper._handle_button_down(99)  # unmapped
            mapper._handle_button_down(0)
            mapper._handle_button_up(99)   # unmapped
            mapper._handle_button_up(0)
            self.assertEqual(mock_send.call_args_list, [call("a"), call("b")])

    def test_pressed_buttons_set_tracks_state_independently(self):
        """_pressed_buttons must reflect only the buttons currently held down."""
        mapper = _make_mapper({
            "0": {"mode": "press", "key": "a"},
            "1": {"mode": "press", "key": "b"},
        })
        self.assertEqual(mapper._pressed_buttons, set())
        mapper._handle_button_down(0)
        self.assertIn(0, mapper._pressed_buttons)
        self.assertNotIn(1, mapper._pressed_buttons)
        mapper._handle_button_down(1)
        self.assertIn(0, mapper._pressed_buttons)
        self.assertIn(1, mapper._pressed_buttons)
        mapper._handle_button_up(0)
        self.assertNotIn(0, mapper._pressed_buttons)
        self.assertIn(1, mapper._pressed_buttons)
        mapper._handle_button_up(1)
        self.assertEqual(mapper._pressed_buttons, set())


# ---------------------------------------------------------------------------
# load_device_config – learn-mode config loading (mappings not required)
# ---------------------------------------------------------------------------

class TestLoadDeviceConfig(unittest.TestCase):
    """Verify that load_device_config accepts configs without a 'mappings' key."""

    def _write_config(self, tmp_dir: str, data: dict) -> None:
        path = os.path.join(tmp_dir, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        # Point the module at this temporary file.
        gamepad_mapper.CONFIG_FILE = path

    def tearDown(self):
        # Reset CONFIG_FILE to its original value after each test.
        gamepad_mapper.CONFIG_FILE = "config.json"

    def test_minimal_config_with_guid_only(self):
        """A config with only target_guid and no mappings must succeed."""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_config(tmp, {"target_guid": "abc123"})
            config = gamepad_mapper.load_device_config()
        self.assertEqual(config["target_guid"], "abc123")
        self.assertNotIn("mappings", config)

    def test_minimal_config_with_name_only(self):
        """A config with only target_name_contains and no mappings must succeed."""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_config(tmp, {"target_name_contains": "Button Box"})
            config = gamepad_mapper.load_device_config()
        self.assertEqual(config["target_name_contains"], "Button Box")

    def test_full_config_also_accepted(self):
        """A full config (with mappings) must also be accepted by load_device_config."""
        full = {
            "target_guid": "abc123",
            "mappings": {"0": {"mode": "press", "key": "a"}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            self._write_config(tmp, full)
            config = gamepad_mapper.load_device_config()
        self.assertIn("mappings", config)

    def test_missing_device_fields_exits(self):
        """A config with no device identification must cause sys.exit."""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_config(tmp, {"mappings": {}})
            with self.assertRaises(SystemExit):
                gamepad_mapper.load_device_config()

    def test_missing_config_file_exits(self):
        """When config.json does not exist, load_device_config must sys.exit."""
        gamepad_mapper.CONFIG_FILE = os.path.join(
            tempfile.gettempdir(), "nonexistent_joymapper_config.json"
        )
        with self.assertRaises(SystemExit):
            gamepad_mapper.load_device_config()


# ---------------------------------------------------------------------------
# _init_pygame – hidden display creation for event-pump fix
# ---------------------------------------------------------------------------

class TestInitPygame(unittest.TestCase):
    """Verify that _init_pygame creates a hidden display when none exists."""

    def test_creates_display_when_no_surface_exists(self):
        """_init_pygame must call display.set_mode when get_surface returns None."""
        _pygame_display_stub.get_surface.return_value = None
        _pygame_display_stub.set_mode.reset_mock()

        gamepad_mapper._init_pygame()

        _pygame_display_stub.set_mode.assert_called_once()
        args = _pygame_display_stub.set_mode.call_args
        # First positional arg must be a (1, 1) size tuple.
        self.assertEqual(args[0][0], (1, 1))

    def test_skips_display_when_surface_already_exists(self):
        """_init_pygame must not call display.set_mode when a surface already exists."""
        _pygame_display_stub.get_surface.return_value = MagicMock()  # surface present
        _pygame_display_stub.set_mode.reset_mock()

        gamepad_mapper._init_pygame()

        _pygame_display_stub.set_mode.assert_not_called()
        # Reset for subsequent tests
        _pygame_display_stub.get_surface.return_value = None


if __name__ == "__main__":
    unittest.main()
