from __future__ import annotations

import unittest
from pathlib import Path

from kousen_remote.model import HID_SERVICE_UUID, DeviceRecord
from kousen_remote.profiles import load_profile


PROFILE = Path("profiles/apple-siri-remote-3.json")


class Variant:
    def __init__(self, value: object) -> None:
        self.value = value


class ProfileMatchingTests(unittest.TestCase):
    def test_bluez_properties_unwrap_variants(self) -> None:
        device = DeviceRecord.from_bluez_properties(
            "/org/bluez/hci0/dev_E0_C3_EA_A1_88_77",
            {
                "Address": Variant("E0:C3:EA:A1:88:77"),
                "UUIDs": Variant([HID_SERVICE_UUID.upper()]),
                "ManufacturerData": Variant({0x004C: Variant([1, 2, 3])}),
                "Appearance": Variant(0x03C0),
            },
        )

        self.assertEqual(device.address, "E0:C3:EA:A1:88:77")
        self.assertEqual(device.manufacturer_data[0x004C], b"\x01\x02\x03")
        self.assertIn(HID_SERVICE_UUID, device.uuids)

    def test_known_remote_profile_scores_high(self) -> None:
        profile = load_profile(PROFILE)
        device = DeviceRecord(
            address="E0:C3:EA:A1:88:77",
            address_type="public",
            uuids=(HID_SERVICE_UUID,),
            manufacturer_data={0x004C: bytes.fromhex("07 0d 02 15 03 02 e0 c3 ea a1 88 77 4e 50 4e")},
            appearance=0x03C0,
            modalias="bluetooth:v004Cp0315d0001",
            rssi=-35,
        )

        match = profile.score(device)

        self.assertTrue(match.plausible)
        self.assertGreaterEqual(match.score, 100)
        self.assertIn("vendor/product 004c:0315", match.matched)
        self.assertNotIn("E0:C3:EA:A1:88:77", " ".join(match.matched))

    def test_advertisement_only_candidate_is_plausible(self) -> None:
        profile = load_profile(PROFILE)
        device = DeviceRecord(
            address="AA:BB:CC:DD:EE:FF",
            address_type="public",
            uuids=(HID_SERVICE_UUID,),
            manufacturer_data={0x004C: b"\x01\x02"},
            appearance=0x03C0,
            rssi=-49,
        )

        match = profile.score(device)

        self.assertTrue(match.plausible)
        self.assertIn("modalias bluetooth:v004Cp0315d0001", match.missing)

    def test_unrelated_device_is_not_plausible(self) -> None:
        profile = load_profile(PROFILE)
        device = DeviceRecord(
            address="11:22:33:44:55:66",
            name="Kitchen Light",
            manufacturer_data={0x1234: b"\x00"},
            rssi=-40,
        )

        match = profile.score(device)

        self.assertFalse(match.plausible)


if __name__ == "__main__":
    unittest.main()
