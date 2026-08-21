from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kousen_remote.devices.hidraw import find_hidraw_devices


class HidrawInspectionTests(unittest.TestCase):
    def test_finds_matching_vendor_product_without_fixed_hidraw_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sys_root = root / "sys" / "class" / "hidraw"
            dev_root = root / "dev"
            device_dir = sys_root / "hidraw9" / "device"
            device_dir.mkdir(parents=True)
            dev_root.mkdir()
            (device_dir / "uevent").write_text("HID_ID=0005:004C:0315\n", encoding="utf-8")
            (device_dir / "name").write_text("C08RKX432330\n", encoding="utf-8")

            devices = find_hidraw_devices(vendor_id="004c", product_id="0315", sys_root=sys_root, dev_root=dev_root)

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0].name, "hidraw9")
            self.assertEqual(devices[0].vendor_id, "004c")
            self.assertEqual(devices[0].product_id, "0315")


if __name__ == "__main__":
    unittest.main()
