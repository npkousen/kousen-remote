from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


HID_SERVICE_UUID = "00001812-0000-1000-8000-00805f9b34fb"


def normalize_hex(value: str | int | None, width: int | None = None) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        number = value
    else:
        text = value.strip().lower()
        if text.startswith("0x"):
            text = text[2:]
        if not text:
            return None
        number = int(text, 16)
    text = f"{number:x}"
    if width is not None:
        text = text.zfill(width)
    return text


def normalize_uuid(value: str) -> str:
    return value.strip().lower()


def unwrap_variant(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True)
class DeviceRecord:
    path: str | None = None
    address: str | None = None
    address_type: str | None = None
    name: str | None = None
    alias: str | None = None
    uuids: tuple[str, ...] = ()
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)
    appearance: int | None = None
    modalias: str | None = None
    rssi: int | None = None
    paired: bool | None = None
    bonded: bool | None = None
    trusted: bool | None = None
    connected: bool | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.alias or self.address or self.path or "unknown"

    @property
    def manufacturer_ids(self) -> set[int]:
        return set(self.manufacturer_data)

    @property
    def vendor_product_from_modalias(self) -> tuple[str | None, str | None]:
        if not self.modalias:
            return None, None
        # Example: bluetooth:v004Cp0315d0001
        lowered = self.modalias.lower()
        vendor = None
        product = None
        if "v" in lowered and "p" in lowered:
            try:
                vendor = lowered.split("v", 1)[1].split("p", 1)[0]
                product = lowered.split("p", 1)[1].split("d", 1)[0]
            except IndexError:
                return None, None
        return normalize_hex(vendor, 4), normalize_hex(product, 4)

    @classmethod
    def from_bluez_properties(cls, path: str, properties: dict[str, Any]) -> "DeviceRecord":
        manufacturer_data: dict[int, bytes] = {}
        raw_manufacturer = unwrap_variant(properties.get("ManufacturerData")) or {}
        for key, value in raw_manufacturer.items():
            data = unwrap_variant(value)
            manufacturer_data[int(key)] = bytes(data)

        def prop(name: str) -> Any:
            return unwrap_variant(properties.get(name))

        return cls(
            path=path,
            address=prop("Address"),
            address_type=prop("AddressType"),
            name=prop("Name"),
            alias=prop("Alias"),
            uuids=tuple(normalize_uuid(uuid) for uuid in (prop("UUIDs") or ())),
            manufacturer_data=manufacturer_data,
            appearance=prop("Appearance"),
            modalias=prop("Modalias"),
            rssi=prop("RSSI"),
            paired=prop("Paired"),
            bonded=prop("Bonded"),
            trusted=prop("Trusted"),
            connected=prop("Connected"),
        )
