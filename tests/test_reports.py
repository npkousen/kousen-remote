from __future__ import annotations

import unittest

from kousen_remote.drivers.apple_siri_remote_3 import classify_button_payload
from kousen_remote.mapping import NormalizedAction


class AppleSiriRemoteReportTests(unittest.TestCase):
    def test_release_value_is_classified_without_labeling_button(self) -> None:
        report = classify_button_payload(bytes.fromhex("0000"))

        self.assertIsNotNone(report)
        self.assertEqual(report.state, "release")

    def test_known_press_value_does_not_invent_semantic_label(self) -> None:
        report = classify_button_payload(bytes.fromhex("0200"))

        self.assertIsNotNone(report)
        self.assertEqual(report.state, "press")
        self.assertEqual(report.action, NormalizedAction.VOLUME_UP)

    def test_labeled_values_decode_to_actions(self) -> None:
        cases = {
            "0002": NormalizedAction.NAV_UP,
            "0008": NormalizedAction.NAV_DOWN,
            "0010": NormalizedAction.NAV_LEFT,
            "0004": NormalizedAction.NAV_RIGHT,
            "0800": NormalizedAction.SELECT,
            "4000": NormalizedAction.BACK,
            "0100": NormalizedAction.HOME,
            "0001": NormalizedAction.PLAY_PAUSE,
            "8000": NormalizedAction.MUTE,
            "0200": NormalizedAction.VOLUME_UP,
            "0400": NormalizedAction.VOLUME_DOWN,
            "1000": NormalizedAction.POWER,
            "2000": NormalizedAction.SIRI,
        }

        for raw, action in cases.items():
            with self.subTest(raw=raw):
                report = classify_button_payload(bytes.fromhex(raw))
                self.assertIsNotNone(report)
                self.assertEqual(report.action, action)

    def test_touch_sized_payload_is_not_classified_as_button(self) -> None:
        report = classify_button_payload(bytes.fromhex("323cd300522ee7bcb32764"))

        self.assertIsNone(report)


if __name__ == "__main__":
    unittest.main()
