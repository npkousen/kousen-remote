from __future__ import annotations

import unittest

from kousen_remote.diagnostics import BtmonParser


class BtmonParserTests(unittest.TestCase):
    def test_parses_known_button_notification(self) -> None:
        parser = BtmonParser()

        self.assertIsNone(parser.parse_line("        Handle: 0x0039\n"))
        event = parser.parse_line("          Data: 0200\n")

        self.assertIsNotNone(event)
        self.assertEqual(event.handle, "0x0039")
        self.assertEqual(event.raw, "0200")
        self.assertEqual(event.kind, "button")
        self.assertEqual(event.state, "press")
        self.assertTrue(event.known)

    def test_parses_release_notification(self) -> None:
        parser = BtmonParser()
        parser.parse_line("        Handle: 0x0039\n")

        event = parser.parse_line("          Data: 0000\n")

        self.assertIsNotNone(event)
        self.assertEqual(event.kind, "button")
        self.assertEqual(event.state, "release")

    def test_parses_touch_sized_payload(self) -> None:
        parser = BtmonParser()
        parser.parse_line("        Handle: 0x003d\n")

        event = parser.parse_line("          Data: 323cd300522ee7bcb32764\n")

        self.assertIsNotNone(event)
        self.assertEqual(event.handle, "0x003d")
        self.assertEqual(event.kind, "touch")


if __name__ == "__main__":
    unittest.main()
