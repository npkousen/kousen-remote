from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kousen_remote.model import normalize_hex


SYS_HIDRAW = Path("/sys/class/hidraw")
DEV = Path("/dev")


@dataclass(frozen=True)
class HidrawDevice:
    name: str
    dev_path: Path
    sys_path: Path
    hid_id: str | None
    vendor_id: str | None
    product_id: str | None
    device_name: str | None
    uniq: str | None
    phys: str | None

    @property
    def matches_apple_siri_remote_3(self) -> bool:
        return self.vendor_id == "004c" and self.product_id == "0315"


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _parse_hid_id(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    parts = raw.split(":")
    if len(parts) < 3:
        return None, None
    return normalize_hex(parts[1], 4), normalize_hex(parts[2], 4)


def inspect_hidraw(name: str, *, sys_root: Path = SYS_HIDRAW, dev_root: Path = DEV) -> HidrawDevice | None:
    sys_path = sys_root / name
    device_path = sys_path / "device"
    hid_id = _read_text(device_path / "uevent")
    hid_line = None
    if hid_id:
        for line in hid_id.splitlines():
            if line.startswith("HID_ID="):
                hid_line = line.removeprefix("HID_ID=")
                break
    vendor_id, product_id = _parse_hid_id(hid_line)
    if not sys_path.exists():
        return None
    return HidrawDevice(
        name=name,
        dev_path=dev_root / name,
        sys_path=sys_path,
        hid_id=hid_line,
        vendor_id=vendor_id,
        product_id=product_id,
        device_name=_read_text(device_path / "name"),
        uniq=_read_text(device_path / "uniq"),
        phys=_read_text(device_path / "phys"),
    )


def find_hidraw_devices(
    *,
    vendor_id: str | None = None,
    product_id: str | None = None,
    sys_root: Path = SYS_HIDRAW,
    dev_root: Path = DEV,
) -> list[HidrawDevice]:
    vendor = normalize_hex(vendor_id, 4)
    product = normalize_hex(product_id, 4)
    devices: list[HidrawDevice] = []
    if not sys_root.exists():
        return devices
    for entry in sorted(sys_root.iterdir(), key=lambda item: item.name):
        inspected = inspect_hidraw(entry.name, sys_root=sys_root, dev_root=dev_root)
        if inspected is None:
            continue
        if vendor is not None and inspected.vendor_id != vendor:
            continue
        if product is not None and inspected.product_id != product:
            continue
        devices.append(inspected)
    return devices
