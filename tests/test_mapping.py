from __future__ import annotations

import unittest

from kousen_remote.mapping import MappingConfig, NormalizedAction, RichEventType


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
        self.assertIsNone(mapping.key_for(NormalizedAction.POWER))


if __name__ == "__main__":
    unittest.main()
