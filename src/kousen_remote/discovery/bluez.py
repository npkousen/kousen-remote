from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from kousen_remote.model import HID_SERVICE_UUID, DeviceRecord


BLUEZ_SERVICE = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"


class BlueZUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class BlueZDeviceRef:
    path: str
    record: DeviceRecord


def _load_dbus_next() -> tuple[Any, Any, Any]:
    try:
        from dbus_next import BusType, Variant
        from dbus_next.aio import MessageBus
    except ImportError as exc:
        raise BlueZUnavailable(
            "dbus-next is required for live BlueZ access. Install with: python -m pip install -e ."
        ) from exc
    return BusType, MessageBus, Variant


class BlueZClient:
    def __init__(self) -> None:
        self._bus: Any | None = None
        self._object_manager: Any | None = None

    async def connect(self) -> None:
        BusType, MessageBus, _Variant = _load_dbus_next()
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        root_introspection = await self._bus.introspect(BLUEZ_SERVICE, "/")
        root = self._bus.get_proxy_object(BLUEZ_SERVICE, "/", root_introspection)
        self._object_manager = root.get_interface(OBJECT_MANAGER_IFACE)

    async def managed_objects(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._object_manager is None:
            await self.connect()
        return await self._object_manager.call_get_managed_objects()

    async def default_adapter_path(self) -> str:
        objects = await self.managed_objects()
        for path, interfaces in objects.items():
            if ADAPTER_IFACE in interfaces:
                return path
        raise BlueZUnavailable("No BlueZ adapter was found on the system bus.")

    async def adapter(self, path: str | None = None) -> Any:
        if self._bus is None:
            await self.connect()
        adapter_path = path or await self.default_adapter_path()
        introspection = await self._bus.introspect(BLUEZ_SERVICE, adapter_path)
        adapter_object = self._bus.get_proxy_object(BLUEZ_SERVICE, adapter_path, introspection)
        return adapter_object.get_interface(ADAPTER_IFACE)

    async def devices(self) -> list[BlueZDeviceRef]:
        objects = await self.managed_objects()
        refs: list[BlueZDeviceRef] = []
        for path, interfaces in objects.items():
            properties = interfaces.get(DEVICE_IFACE)
            if properties is not None:
                refs.append(BlueZDeviceRef(path=path, record=DeviceRecord.from_bluez_properties(path, properties)))
        return refs

    async def scan(self, seconds: float, *, hid_only: bool = True) -> list[DeviceRecord]:
        _BusType, _MessageBus, Variant = _load_dbus_next()
        adapter = await self.adapter()
        discovery_filter: dict[str, Any] = {
            "Transport": Variant("s", "le"),
            "DuplicateData": Variant("b", False),
        }
        if hid_only:
            discovery_filter["UUIDs"] = Variant("as", [HID_SERVICE_UUID])
        await adapter.call_set_discovery_filter(discovery_filter)
        await adapter.call_start_discovery()
        try:
            await asyncio.sleep(seconds)
            refs = await self.devices()
        finally:
            await adapter.call_stop_discovery()
        return [ref.record for ref in refs]

    async def find_device(self, address_or_path: str) -> BlueZDeviceRef:
        wanted = address_or_path.lower()
        for ref in await self.devices():
            if ref.path == address_or_path or (ref.record.address and ref.record.address.lower() == wanted):
                return ref
        raise BlueZUnavailable(f"BlueZ device not found: {address_or_path}")

    async def pair(self, address_or_path: str, *, trust: bool = True, connect: bool = True) -> DeviceRecord:
        _BusType, _MessageBus, Variant = _load_dbus_next()
        ref = await self.find_device(address_or_path)
        if self._bus is None:
            await self.connect()
        introspection = await self._bus.introspect(BLUEZ_SERVICE, ref.path)
        device_object = self._bus.get_proxy_object(BLUEZ_SERVICE, ref.path, introspection)
        device = device_object.get_interface(DEVICE_IFACE)
        props = device_object.get_interface(PROPERTIES_IFACE)

        if not ref.record.paired:
            await device.call_pair()
        if trust:
            await props.call_set(DEVICE_IFACE, "Trusted", Variant("b", True))
        if connect:
            await device.call_connect()
        return (await self.find_device(ref.path)).record


def scan_blocking(seconds: float, *, hid_only: bool = True) -> list[DeviceRecord]:
    return asyncio.run(BlueZClient().scan(seconds, hid_only=hid_only))


def devices_blocking() -> list[DeviceRecord]:
    return [ref.record for ref in asyncio.run(BlueZClient().devices())]


def pair_blocking(address_or_path: str, *, trust: bool = True, connect: bool = True) -> DeviceRecord:
    return asyncio.run(BlueZClient().pair(address_or_path, trust=trust, connect=connect))
