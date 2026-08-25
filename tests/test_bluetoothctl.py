from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from kousen_remote.discovery.bluetoothctl import discovered_addresses, find_blocking, listed_addresses, parse_info
from kousen_remote.model import HID_SERVICE_UUID
from kousen_remote.profiles import load_bundled_profiles


SCAN_OUTPUT = """
[NEW] Device AA:AA:AA:AA:AA:AA Noise
[CHG] Device E0:C3:EA:A4:3E:05 RSSI: -42
[CHG] Device E0:C3:EA:A4:3E:05 ManufacturerData Key: 0x004c
"""


INFO_OUTPUT = """
Device E0:C3:EA:A4:3E:05 (public)
    Alias: E0-C3-EA-A4-3E-05
    Appearance: 0x03c0 (960)
    Paired: no
    Bonded: no
    Trusted: no
    Blocked: no
    Connected: no
    WakeAllowed: no
    LegacyPairing: no
    UUID: Human Interface Device    (00001812-0000-1000-8000-00805f9b34fb)
    ManufacturerData.Key: 0x004c (76)
    ManufacturerData.Value:
      07 0d 02 15 03 02 e0 c3 ea a4 3e 05 4d 4e 4e  .............MNN
    AdvertisingFlags:
      06
"""


class BluetoothCtlParsingTests(unittest.TestCase):
    def test_discovers_unique_new_and_changed_device_addresses(self) -> None:
        self.assertEqual(discovered_addresses(SCAN_OUTPUT), ["AA:AA:AA:AA:AA:AA", "E0:C3:EA:A4:3E:05"])

    def test_lists_known_bluetoothctl_device_addresses(self) -> None:
        output = """
Device 11:22:33:44:55:66 Keyboard
Device E0:C3:EA:A4:3E:05 E0-C3-EA-A4-3E-05
"""

        self.assertEqual(listed_addresses(output), ["11:22:33:44:55:66", "E0:C3:EA:A4:3E:05"])

    def test_parses_siri_remote_info_signature(self) -> None:
        device = parse_info(INFO_OUTPUT)

        self.assertEqual(device.address, "E0:C3:EA:A4:3E:05")
        self.assertEqual(device.appearance, 0x03C0)
        self.assertEqual(
            device.manufacturer_data[0x004C],
            bytes.fromhex("07 0d 02 15 03 02 e0 c3 ea a4 3e 05 4d 4e 4e"),
        )
        self.assertIn(HID_SERVICE_UUID, device.uuids)
        self.assertFalse(device.paired)
        self.assertFalse(device.connected)

    def test_parses_real_bluez_dotted_manufacturer_data_fields(self) -> None:
        device = parse_info(
            """
Device E0:C3:EA:A4:3E:05 (public)
    ManufacturerData.Key: 0x004c (76)
    ManufacturerData.Value:
      07 0d 02 15 03 02 e0 c3 ea a4 3e 05 4d 4e 4e  .............MNN
"""
        )

        self.assertEqual(
            device.manufacturer_data,
            {0x004C: bytes.fromhex("07 0d 02 15 03 02 e0 c3 ea a4 3e 05 4d 4e 4e")},
        )

    def test_sample_signature_scores_85_without_modalias(self) -> None:
        device = parse_info(INFO_OUTPUT)
        profile = load_bundled_profiles()[0]

        match = profile.score(device)

        self.assertEqual(match.score, 85)
        self.assertEqual(
            match.matched,
            (
                "Apple manufacturer data 0x004c",
                f"Bluetooth HID service {HID_SERVICE_UUID}",
                "HID remote-control appearance 0x03c0",
            ),
        )

    def test_find_blocking_runs_bluetoothctl_scan_then_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bluetoothctl = Path(tmp_dir) / "bluetoothctl"
            fake_bluetoothctl.write_text(
                f"""#!{sys.executable}
import sys

if len(sys.argv) > 1 and sys.argv[1] == "info":
    print({INFO_OUTPUT!r})
    raise SystemExit(0)
if len(sys.argv) > 1 and sys.argv[1] == "devices":
    raise SystemExit(0)

for raw_line in sys.stdin.buffer:
    command = raw_line.decode("utf-8").strip()
    if command == "scan on":
        print("[CHG] Device E0:C3:EA:A4:3E:05 RSSI: -42", flush=True)
    elif command == "quit":
        break
""",
                encoding="utf-8",
            )
            os.chmod(fake_bluetoothctl, 0o755)

            result = find_blocking(0.2, bluetoothctl_path=str(fake_bluetoothctl))

        self.assertEqual(len(result.devices), 1)
        self.assertEqual(result.devices[0].address, "E0:C3:EA:A4:3E:05")
        self.assertEqual(
            result.devices[0].manufacturer_data[0x004C],
            bytes.fromhex("07 0d 02 15 03 02 e0 c3 ea a4 3e 05 4d 4e 4e"),
        )

    def test_find_blocking_scores_known_device_when_scan_has_no_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bluetoothctl = Path(tmp_dir) / "bluetoothctl"
            fake_bluetoothctl.write_text(
                f"""#!{sys.executable}
import sys

if len(sys.argv) > 1 and sys.argv[1] == "info":
    print({INFO_OUTPUT!r})
    raise SystemExit(0)
if len(sys.argv) > 1 and sys.argv[1] == "devices":
    print("Device E0:C3:EA:A4:3E:05 E0-C3-EA-A4-3E-05")
    raise SystemExit(0)

for raw_line in sys.stdin.buffer:
    command = raw_line.decode("utf-8").strip()
    if command == "quit":
        break
""",
                encoding="utf-8",
            )
            os.chmod(fake_bluetoothctl, 0o755)

            result = find_blocking(0.2, bluetoothctl_path=str(fake_bluetoothctl))

        self.assertEqual(len(result.devices), 1)
        match = load_bundled_profiles()[0].score(result.devices[0])
        self.assertEqual(match.score, 85)


if __name__ == "__main__":
    unittest.main()
