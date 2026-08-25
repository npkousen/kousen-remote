from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from kousen_remote.model import HID_SERVICE_UUID, DeviceRecord, unwrap_variant


BLUEZ_SERVICE = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHARACTERISTIC_IFACE = "org.bluez.GattCharacteristic1"
GATT_DESCRIPTOR_IFACE = "org.bluez.GattDescriptor1"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"


class BlueZUnavailable(RuntimeError):
    pass


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class BlueZDeviceRef:
    path: str
    record: DeviceRecord


@dataclass(frozen=True)
class GattObject:
    path: str
    kind: str
    uuid: str | None
    flags: tuple[str, ...] = ()
    service: str | None = None
    characteristic: str | None = None
    notifying: bool | None = None


@dataclass(frozen=True)
class GattNotification:
    path: str
    value: bytes


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
            try:
                await asyncio.wait_for(adapter.call_stop_discovery(), timeout=3.0)
            except Exception:
                pass
        return [ref.record for ref in refs]

    async def find_device(self, address_or_path: str) -> BlueZDeviceRef:
        wanted = address_or_path.lower()
        for ref in await self.devices():
            if ref.path == address_or_path or (ref.record.address and ref.record.address.lower() == wanted):
                return ref
        raise BlueZUnavailable(f"BlueZ device not found: {address_or_path}")

    async def _run_operation(self, operation: str, fallback_command: str, coro: Any, timeout: float | None) -> Any:
        try:
            if timeout is None:
                return await coro
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise BlueZUnavailable(
                f"Timed out while {operation} after {timeout:g} seconds. "
                f"Try the bluetoothctl fallback: bluetoothctl {fallback_command} <address>"
            ) from exc

    async def pair(
        self,
        address_or_path: str,
        *,
        trust: bool = True,
        connect: bool = True,
        timeout: float | None = 30.0,
        progress: ProgressCallback | None = None,
    ) -> DeviceRecord:
        _BusType, _MessageBus, Variant = _load_dbus_next()
        if progress is not None:
            progress(f"Finding BlueZ device {address_or_path}...")
        ref = await self.find_device(address_or_path)
        if self._bus is None:
            await self.connect()
        introspection = await self._bus.introspect(BLUEZ_SERVICE, ref.path)
        device_object = self._bus.get_proxy_object(BLUEZ_SERVICE, ref.path, introspection)
        device = device_object.get_interface(DEVICE_IFACE)
        props = device_object.get_interface(PROPERTIES_IFACE)

        if not ref.record.paired:
            if progress is not None:
                progress(f"Pairing {address_or_path}...")
            await self._run_operation("pairing", "pair", device.call_pair(), timeout)
        elif progress is not None:
            progress(f"{address_or_path} is already paired.")
        if trust:
            if progress is not None:
                progress(f"Trusting {address_or_path}...")
            await self._run_operation(
                "trusting",
                "trust",
                props.call_set(DEVICE_IFACE, "Trusted", Variant("b", True)),
                timeout,
            )
        if connect:
            if progress is not None:
                progress(f"Connecting {address_or_path}...")
            await self._run_operation("connecting", "connect", device.call_connect(), timeout)
        if progress is not None:
            progress(f"Refreshing {address_or_path}...")
        return (await self.find_device(ref.path)).record

    async def connect_device(self, address_or_path: str, *, timeout: float | None = 30.0) -> DeviceRecord:
        ref = await self.find_device(address_or_path)
        if ref.record.connected:
            return ref.record
        if self._bus is None:
            await self.connect()
        introspection = await self._bus.introspect(BLUEZ_SERVICE, ref.path)
        device_object = self._bus.get_proxy_object(BLUEZ_SERVICE, ref.path, introspection)
        device = device_object.get_interface(DEVICE_IFACE)
        try:
            await self._run_operation("connecting", "connect", device.call_connect(), timeout)
        except Exception as exc:
            if "AlreadyConnected" not in str(exc):
                raise BlueZUnavailable(f"Could not connect to {address_or_path}: {exc}") from exc
        return (await self.find_device(ref.path)).record

    async def gatt_objects(self, address_or_path: str) -> list[GattObject]:
        ref = await self.find_device(address_or_path)
        objects = await self.managed_objects()
        gatt_objects: list[GattObject] = []
        for path, interfaces in objects.items():
            if not path.startswith(ref.path + "/"):
                continue

            service = interfaces.get(GATT_SERVICE_IFACE)
            if service is not None:
                uuid = unwrap_variant(service.get("UUID"))
                gatt_objects.append(
                    GattObject(
                        path=path,
                        kind="service",
                        uuid=str(uuid) if uuid is not None else None,
                    )
                )

            characteristic = interfaces.get(GATT_CHARACTERISTIC_IFACE)
            if characteristic is not None:
                uuid = unwrap_variant(characteristic.get("UUID"))
                flags = unwrap_variant(characteristic.get("Flags")) or ()
                service_path = unwrap_variant(characteristic.get("Service"))
                notifying = unwrap_variant(characteristic.get("Notifying"))
                gatt_objects.append(
                    GattObject(
                        path=path,
                        kind="characteristic",
                        uuid=str(uuid) if uuid is not None else None,
                        flags=tuple(str(flag) for flag in flags),
                        service=str(service_path) if service_path is not None else None,
                        notifying=bool(notifying) if notifying is not None else None,
                    )
                )

            descriptor = interfaces.get(GATT_DESCRIPTOR_IFACE)
            if descriptor is not None:
                uuid = unwrap_variant(descriptor.get("UUID"))
                flags = unwrap_variant(descriptor.get("Flags")) or ()
                characteristic_path = unwrap_variant(descriptor.get("Characteristic"))
                gatt_objects.append(
                    GattObject(
                        path=path,
                        kind="descriptor",
                        uuid=str(uuid) if uuid is not None else None,
                        flags=tuple(str(flag) for flag in flags),
                        characteristic=str(characteristic_path) if characteristic_path is not None else None,
                    )
                )
        return sorted(gatt_objects, key=lambda item: item.path)

    async def resolve_gatt_path(self, address_or_path: str, target: str) -> str:
        if target.startswith("/"):
            return target
        ref = await self.find_device(address_or_path)
        objects = await self.managed_objects()
        suffix = "/" + target
        matches = [
            path
            for path, interfaces in objects.items()
            if path.startswith(ref.path + "/")
            and path.endswith(suffix)
            and (GATT_CHARACTERISTIC_IFACE in interfaces or GATT_DESCRIPTOR_IFACE in interfaces)
        ]
        if not matches:
            raise BlueZUnavailable(f"GATT target not found for {address_or_path}: {target}")
        if len(matches) > 1:
            raise BlueZUnavailable(f"GATT target is ambiguous for {address_or_path}: {target}")
        return matches[0]

    async def _gatt_proxy(self, path: str) -> tuple[Any, Any, str]:
        if self._bus is None:
            await self.connect()
        introspection = await self._bus.introspect(BLUEZ_SERVICE, path)
        proxy_object = self._bus.get_proxy_object(BLUEZ_SERVICE, path, introspection)
        objects = await self.managed_objects()
        interfaces = objects.get(path, {})
        if GATT_CHARACTERISTIC_IFACE in interfaces:
            return proxy_object, proxy_object.get_interface(GATT_CHARACTERISTIC_IFACE), GATT_CHARACTERISTIC_IFACE
        if GATT_DESCRIPTOR_IFACE in interfaces:
            return proxy_object, proxy_object.get_interface(GATT_DESCRIPTOR_IFACE), GATT_DESCRIPTOR_IFACE
        raise BlueZUnavailable(f"Not a GATT characteristic or descriptor: {path}")

    async def read_gatt(self, address_or_path: str, target: str) -> tuple[str, bytes]:
        path = await self.resolve_gatt_path(address_or_path, target)
        _proxy_object, iface, _iface_name = await self._gatt_proxy(path)
        value = await iface.call_read_value({})
        return path, bytes(value)

    async def write_gatt(self, address_or_path: str, target: str, value: bytes) -> str:
        path = await self.resolve_gatt_path(address_or_path, target)
        _proxy_object, iface, _iface_name = await self._gatt_proxy(path)
        await iface.call_write_value(value, {})
        return path

    async def notify_gatt(
        self,
        address_or_path: str,
        target: str,
        seconds: float | None,
        queue: asyncio.Queue[GattNotification],
    ) -> str:
        path = await self.resolve_gatt_path(address_or_path, target)
        proxy_object, characteristic, iface_name = await self._gatt_proxy(path)
        if iface_name != GATT_CHARACTERISTIC_IFACE:
            raise BlueZUnavailable("Notifications can only be started on GATT characteristics.")
        properties = proxy_object.get_interface(PROPERTIES_IFACE)

        def on_properties_changed(interface_name: str, changed: dict[str, Any], _invalidated: list[str]) -> None:
            if interface_name != GATT_CHARACTERISTIC_IFACE or "Value" not in changed:
                return
            value = unwrap_variant(changed["Value"])
            queue.put_nowait(GattNotification(path=path, value=bytes(value)))

        properties.on_properties_changed(on_properties_changed)
        started = False
        try:
            await characteristic.call_start_notify()
            started = True
            if seconds is None:
                while True:
                    await asyncio.sleep(3600)
            else:
                await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise BlueZUnavailable(f"GATT notification failed for {path}: {exc}") from exc
        finally:
            if started:
                try:
                    await characteristic.call_stop_notify()
                except Exception:
                    pass


async def _with_timeout(coro: Any, timeout: float) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise BlueZUnavailable(f"BlueZ D-Bus call timed out after {timeout:g} seconds.") from exc


def scan_blocking(seconds: float, *, hid_only: bool = True, timeout: float | None = None) -> list[DeviceRecord]:
    scan_timeout = timeout if timeout is not None else max(seconds + 5.0, 10.0)
    return asyncio.run(_with_timeout(BlueZClient().scan(seconds, hid_only=hid_only), scan_timeout))


def devices_blocking(*, timeout: float = 8.0) -> list[DeviceRecord]:
    return [ref.record for ref in asyncio.run(_with_timeout(BlueZClient().devices(), timeout))]


def pair_blocking(
    address_or_path: str,
    *,
    trust: bool = True,
    connect: bool = True,
    timeout: float | None = 30.0,
    progress: ProgressCallback | None = None,
) -> DeviceRecord:
    return asyncio.run(
        BlueZClient().pair(address_or_path, trust=trust, connect=connect, timeout=timeout, progress=progress)
    )


def connect_device_blocking(address_or_path: str, *, timeout: float | None = 30.0) -> DeviceRecord:
    return asyncio.run(BlueZClient().connect_device(address_or_path, timeout=timeout))


def gatt_objects_blocking(address_or_path: str) -> list[GattObject]:
    return asyncio.run(BlueZClient().gatt_objects(address_or_path))


def read_gatt_blocking(address_or_path: str, target: str) -> tuple[str, bytes]:
    return asyncio.run(BlueZClient().read_gatt(address_or_path, target))


def write_gatt_blocking(address_or_path: str, target: str, value: bytes) -> str:
    return asyncio.run(BlueZClient().write_gatt(address_or_path, target, value))
