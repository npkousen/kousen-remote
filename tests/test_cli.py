from __future__ import annotations

import unittest

from kousen_remote.cli.main import build_parser


class CliParserTests(unittest.TestCase):
    def test_pair_accepts_timeout_before_device(self) -> None:
        args = build_parser().parse_args(["pair", "--timeout", "30", "E0:C3:EA:A4:3E:05"])

        self.assertEqual(args.command, "pair")
        self.assertEqual(args.timeout, 30.0)
        self.assertEqual(args.backend, "auto")
        self.assertEqual(args.device, "E0:C3:EA:A4:3E:05")

    def test_pair_accepts_bluetoothctl_backend(self) -> None:
        args = build_parser().parse_args(["pair", "--backend", "bluetoothctl", "E0:C3:EA:A4:3E:05"])

        self.assertEqual(args.backend, "bluetoothctl")


if __name__ == "__main__":
    unittest.main()
