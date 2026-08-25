from __future__ import annotations

import json
from importlib import resources
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import DeviceRecord, normalize_hex, normalize_uuid


@dataclass(frozen=True)
class ProfileMatch:
    profile_id: str
    score: int
    matched: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def plausible(self) -> bool:
        return self.score >= 25


@dataclass(frozen=True)
class DeviceProfile:
    id: str
    name: str
    match: dict[str, Any]
    features: dict[str, bool]
    reports: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceProfile":
        return cls(
            id=data["id"],
            name=data["name"],
            match=data.get("match", {}),
            features=data.get("features", {}),
            reports=data.get("reports", {}),
        )

    def score(self, device: DeviceRecord) -> ProfileMatch:
        score = 0
        matched: list[str] = []
        missing: list[str] = []

        manufacturer_id = normalize_hex(self.match.get("manufacturer_id"), 4)
        if manufacturer_id is not None:
            expected = int(manufacturer_id, 16)
            if expected in device.manufacturer_ids:
                score += 35
                matched.append(f"Apple manufacturer data 0x{manufacturer_id}")
            else:
                missing.append(f"manufacturer data 0x{manufacturer_id}")

        hid_service = self.match.get("hid_service")
        if hid_service is not None:
            expected_uuid = normalize_uuid(hid_service)
            if expected_uuid in device.uuids:
                score += 30
                matched.append(f"Bluetooth HID service {expected_uuid}")
            else:
                missing.append(f"HID service {expected_uuid}")

        appearance = normalize_hex(self.match.get("appearance"), 4)
        if appearance is not None:
            expected = int(appearance, 16)
            if device.appearance == expected:
                score += 20
                matched.append(f"HID remote-control appearance 0x{appearance}")
            else:
                missing.append(f"appearance 0x{appearance}")

        modalias = self.match.get("modalias")
        matched_modalias = False
        if modalias is not None:
            if device.modalias and str(modalias).lower() in device.modalias.lower():
                score += 50
                matched_modalias = True
                matched.append(f"Bluetooth modalias {modalias}")
            else:
                missing.append(f"modalias {modalias}")

        vendor_id = normalize_hex(self.match.get("vendor_id"), 4)
        product_id = normalize_hex(self.match.get("product_id"), 4)
        found_vendor, found_product = device.vendor_product_from_modalias
        if vendor_id and product_id and found_vendor and found_product and not matched_modalias:
            if vendor_id == found_vendor and product_id == found_product:
                score += 45
                matched.append(f"vendor/product {vendor_id}:{product_id}")
            else:
                missing.append(f"vendor/product {vendor_id}:{product_id}")

        return ProfileMatch(self.id, score, tuple(matched), tuple(missing))


def load_profile(path: Path) -> DeviceProfile:
    with path.open("r", encoding="utf-8") as handle:
        return DeviceProfile.from_dict(json.load(handle))


def load_profiles(directory: Path) -> list[DeviceProfile]:
    return [load_profile(path) for path in sorted(directory.glob("*.json"))]


def load_bundled_profiles() -> list[DeviceProfile]:
    profile_dir = resources.files("kousen_remote.profile_data")
    profiles: list[DeviceProfile] = []
    for resource in sorted(profile_dir.iterdir(), key=lambda item: item.name):
        if resource.name.endswith(".json"):
            profiles.append(DeviceProfile.from_dict(json.loads(resource.read_text(encoding="utf-8"))))
    return profiles
