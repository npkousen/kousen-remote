from __future__ import annotations

import unittest

from kousen_remote.drivers.apple_siri_remote_3 import classify_button_payload


class AppleSiriRemoteReportTests(unittest.TestCase):
    def test_release_value_is_classified_without_labeling_button(self) -> None:
        report = classify_button_payload(bytes.fromhex("0000"))

        self.assertIsNotNone(report)
        self.assertEqual(report.state, "release")

    def test_known_press_value_does_not_invent_semantic_label(self) -> None:
        report = classify_button_payload(bytes.fromhex("0200"))

        self.assertIsNotNone(report)
        self.assertEqual(report.state, "press")
        self.assertIn("semantic label not established", report.note)

    def test_touch_sized_payload_is_not_classified_as_button(self) -> None:
        report = classify_button_payload(bytes.fromhex("323cd300522ee7bcb32764"))

        self.assertIsNone(report)


if __name__ == "__main__":
    unittest.main()
