from __future__ import annotations

import unittest
from pathlib import Path

from kousen_remote.mapping import MappingConfig, NormalizedAction, RichEventType, load_mapping


class MappingTests(unittest.TestCase):
    def test_required_actions_exist(self) -> None:
        required = {
            "NAV_UP",
            "NAV_DOWN",
            "NAV_LEFT",
            "NAV_RIGHT",
            "SELECT",
            "BACK",
            "HOME",
            "PLAY_PAUSE",
            "VOLUME_UP",
            "VOLUME_DOWN",
            "MUTE",
            "POWER",
            "SIRI",
        }

        self.assertTrue(required.issubset({action.value for action in NormalizedAction}))

    def test_rich_event_types_are_reserved(self) -> None:
        self.assertEqual(RichEventType.SWIPE_LEFT.value, "SWIPE_LEFT")
        self.assertEqual(RichEventType.TOUCH_MOVE.value, "TOUCH_MOVE")

    def test_default_mapping_separates_actions_from_key_codes(self) -> None:
        mapping = MappingConfig.default()

        self.assertEqual(mapping.key_for(NormalizedAction.NAV_UP), "KEY_UP")
        self.assertEqual(mapping.key_for(NormalizedAction.SELECT), "KEY_ENTER")
        self.assertEqual(mapping.key_for(NormalizedAction.BACK), "KEY_ESC")
        self.assertEqual(mapping.key_for(NormalizedAction.SIRI), "KEY_F13")
        self.assertIsNone(mapping.key_for(NormalizedAction.POWER))

    def test_checked_in_kiosk_mapping_loads(self) -> None:
        mapping = load_mapping(Path("mappings/kiosk-browser.json"))

        self.assertEqual(mapping.key_for(NormalizedAction.PLAY_PAUSE), "KEY_SPACE")
        self.assertEqual(mapping.key_for(NormalizedAction.VOLUME_UP), "KEY_VOLUMEUP")
        self.assertIsNone(mapping.key_for(NormalizedAction.POWER))

    def test_checked_in_kousen_control_mapping_loads(self) -> None:
        mapping = load_mapping(Path("mappings/kousen-control.json"))

        self.assertEqual(mapping.key_for(NormalizedAction.NAV_UP), "KEY_F13")
        self.assertEqual(mapping.key_for(NormalizedAction.NAV_RIGHT), "KEY_F14")
        self.assertEqual(mapping.key_for(NormalizedAction.NAV_DOWN), "KEY_F15")
        self.assertEqual(mapping.key_for(NormalizedAction.NAV_LEFT), "KEY_F16")
        self.assertEqual(mapping.key_for(NormalizedAction.SELECT), "KEY_F17")
        self.assertEqual(mapping.key_for(NormalizedAction.POWER), "KEY_F24")
        self.assertEqual(mapping.key_for(NormalizedAction.SIRI), "KEY_HOME")


if __name__ == "__main__":
    unittest.main()
