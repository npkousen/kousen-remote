from __future__ import annotations

import json
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
                score += 25
                matched.append(f"Apple manufacturer data 0x{manufacturer_id}")
            else:
                missing.append(f"manufacturer data 0x{manufacturer_id}")

        hid_service = self.match.get("hid_service")
        if hid_service is not None:
            expected_uuid = normalize_uuid(hid_service)
            if expected_uuid in device.uuids:
                score += 20
                matched.append(f"HID service {expected_uuid}")
            else:
                missing.append(f"HID service {expected_uuid}")

        appearance = normalize_hex(self.match.get("appearance"), 4)
        if appearance is not None:
            expected = int(appearance, 16)
            if device.appearance == expected:
                score += 15
                matched.append(f"appearance 0x{appearance}")
            else:
                missing.append(f"appearance 0x{appearance}")

        modalias = self.match.get("modalias")
        if modalias is not None:
            if device.modalias and device.modalias.lower() == str(modalias).lower():
                score += 50
                matched.append(f"modalias {modalias}")
            else:
                missing.append(f"modalias {modalias}")

        vendor_id = normalize_hex(self.match.get("vendor_id"), 4)
        product_id = normalize_hex(self.match.get("product_id"), 4)
        found_vendor, found_product = device.vendor_product_from_modalias
        if vendor_id and product_id and found_vendor and found_product:
            if vendor_id == found_vendor and product_id == found_product:
                score += 45
                matched.append(f"vendor/product {vendor_id}:{product_id}")
            else:
                missing.append(f"vendor/product {vendor_id}:{product_id}")

        if device.address_type and device.address_type.lower() == "public":
            score += 3
            matched.append("public address")

        if device.rssi is not None and device.rssi >= -60:
            score += 5
            matched.append(f"nearby RSSI {device.rssi} dBm")

        weak_name_terms = tuple(str(term).lower() for term in self.match.get("weak_name_terms", ()))
        haystack = f"{device.name or ''} {device.alias or ''}".lower()
        if weak_name_terms and any(term in haystack for term in weak_name_terms):
            score += 3
            matched.append("weak name/alias hint")

        return ProfileMatch(self.id, score, tuple(matched), tuple(missing))


def load_profile(path: Path) -> DeviceProfile:
    with path.open("r", encoding="utf-8") as handle:
        return DeviceProfile.from_dict(json.load(handle))


def load_profiles(directory: Path) -> list[DeviceProfile]:
    return [load_profile(path) for path in sorted(directory.glob("*.json"))]
