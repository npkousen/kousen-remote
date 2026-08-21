from __future__ import annotations

import unittest
from pathlib import Path

from kousen_remote.discovery.scoring import rank_candidates
from kousen_remote.model import HID_SERVICE_UUID, DeviceRecord
from kousen_remote.profiles import load_profile


class CandidateScoringTests(unittest.TestCase):
    def test_candidates_are_sorted_by_score(self) -> None:
        profile = load_profile(Path("profiles/apple-siri-remote-3.json"))
        weak = DeviceRecord(address="AA:AA:AA:AA:AA:AA", manufacturer_data={0x004C: b"\x01"})
        strong = DeviceRecord(
            address="BB:BB:BB:BB:BB:BB",
            uuids=(HID_SERVICE_UUID,),
            manufacturer_data={0x004C: b"\x01"},
            appearance=0x03C0,
            modalias="bluetooth:v004Cp0315d0001",
        )

        candidates = rank_candidates([weak, strong], [profile], include_low_score=True)

        self.assertEqual(candidates[0].device.address, "BB:BB:BB:BB:BB:BB")
        self.assertGreater(candidates[0].match.score, candidates[1].match.score)


if __name__ == "__main__":
    unittest.main()
