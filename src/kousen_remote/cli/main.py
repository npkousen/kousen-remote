from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from kousen_remote.devices import find_hidraw_devices
from kousen_remote.diagnostics import monitor_btmon, monitor_hidraw
from kousen_remote.discovery.bluez import (
    BlueZClient,
    BlueZUnavailable,
    devices_blocking,
    gatt_objects_blocking,
    pair_blocking,
    read_gatt_blocking,
    scan_blocking,
    write_gatt_blocking,
)
from kousen_remote.discovery.bluetoothctl import BluetoothCtlUnavailable, find_blocking as bluetoothctl_find_blocking
from kousen_remote.discovery.scoring import rank_candidates
from kousen_remote.drivers.apple_siri_remote_3 import classify_button_payload
from kousen_remote.mapping import MappingConfig, load_mapping
from kousen_remote.model import DeviceRecord
from kousen_remote.profiles import DeviceProfile, load_bundled_profiles, load_profiles
from kousen_remote.service.runtime import DEFAULT_BUTTON_CHARACTERISTIC, RuntimeConfig, run_service


DEFAULT_PROFILE_DIR = Path("profiles")


def _load_profiles_or_exit(path: Path) -> list[DeviceProfile]:
    profiles = load_profiles(path)
    if not profiles and path == DEFAULT_PROFILE_DIR:
        profiles = load_bundled_profiles()
    if not profiles:
        raise SystemExit(f"No device profiles found in {path}")
    return profiles


def _print_device(device: DeviceRecord) -> None:
    print(f"{device.display_name}")
    print(f"  Address: {device.address or '-'}")
    print(f"  Path: {device.path or '-'}")
    print(f"  Address type: {device.address_type or '-'}")
    print(f"  RSSI: {device.rssi if device.rssi is not None else '-'}")
    print(f"  Appearance: {hex(device.appearance) if device.appearance is not None else '-'}")
    print(f"  Modalias: {device.modalias or '-'}")
    print(f"  Paired/Bonded/Trusted/Connected: {device.paired}/{device.bonded}/{device.trusted}/{device.connected}")
    if device.manufacturer_data:
        print("  Manufacturer data:")
        for key, value in sorted(device.manufacturer_data.items()):
            print(f"    0x{key:04x}: {value.hex(' ')}")
    if device.uuids:
        print("  UUIDs:")
        for uuid in device.uuids:
            print(f"    {uuid}")


def _print_candidates(devices: list[DeviceRecord], profiles: list[DeviceProfile], include_low_score: bool) -> None:
    candidates = rank_candidates(devices, profiles, include_low_score=include_low_score)
    if not candidates:
        print("No plausible compatible remotes found.")
        return
    for candidate in candidates:
        device = candidate.device
        print(f"{device.display_name}  score={candidate.match.score}  profile={candidate.profile.id}")
        print(f"  Address: {device.address or '-'}")
        print(f"  RSSI: {device.rssi if device.rssi is not None else '-'}")
        print("  Matched:")
        for reason in candidate.match.matched or ("none",):
            print(f"    - {reason}")
        if candidate.match.missing:
            print("  Not yet observed:")
            for reason in candidate.match.missing:
                print(f"    - {reason}")


def _print_pairing_help() -> None:
    print("Put Siri Remote in pairing mode near this PC: Back/Menu + Volume Up for 5 seconds.")
    print("If still nothing, restart remote: TV/Control Center + Volume Down for 5 seconds, wait 10 seconds, then retry.")
    print("Turn off Mac Bluetooth / unplug Apple TV if already paired elsewhere.")


def _print_find_results(devices: list[DeviceRecord], profiles: list[DeviceProfile], *, include_low_score: bool) -> bool:
    candidates = rank_candidates(devices, profiles, include_low_score=include_low_score)
    if not candidates:
        print("No Siri Remote candidate found.")
        _print_pairing_help()
        return False
    for candidate in candidates:
        address = candidate.device.address or candidate.device.display_name
        print(f"Likely Siri Remote candidate: {address} score={candidate.match.score}")
        print(f"Matched: {'; '.join(candidate.match.matched or ('none',))}")
        if candidate.match.missing:
            print(f"Not yet observed: {'; '.join(candidate.match.missing)}")
    return True


def cmd_scan(args: argparse.Namespace) -> int:
    profiles = _load_profiles_or_exit(args.profiles)
    try:
        devices = scan_blocking(args.seconds, hid_only=not args.no_hid_filter, timeout=args.timeout)
    except BlueZUnavailable as exc:
        if args.no_bluetoothctl_fallback:
            print(f"BlueZ scan unavailable: {exc}", file=sys.stderr)
            return 2
        print(f"BlueZ D-Bus scan unavailable, falling back to bluetoothctl: {exc}", file=sys.stderr)
        try:
            result = bluetoothctl_find_blocking(
                args.seconds,
                hid_only=not args.no_hid_filter,
                bluetoothctl_path=args.bluetoothctl,
                info_timeout=args.info_timeout,
            )
        except BluetoothCtlUnavailable as fallback_exc:
            print(f"bluetoothctl scan unavailable: {fallback_exc}", file=sys.stderr)
            return 2
        devices = result.devices
    _print_candidates(devices, profiles, include_low_score=args.all)
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    profiles = _load_profiles_or_exit(args.profiles)
    try:
        devices = devices_blocking(timeout=args.timeout)
    except BlueZUnavailable as exc:
        print(f"BlueZ devices unavailable: {exc}", file=sys.stderr)
        return 2
    _print_candidates(devices, profiles, include_low_score=args.all)
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    profiles = _load_profiles_or_exit(args.profiles)
    try:
        result = bluetoothctl_find_blocking(
            args.seconds,
            hid_only=not args.no_hid_filter,
            bluetoothctl_path=args.bluetoothctl,
            info_timeout=args.info_timeout,
        )
    except BluetoothCtlUnavailable as exc:
        print(f"bluetoothctl discovery unavailable: {exc}", file=sys.stderr)
        _print_pairing_help()
        return 2
    return 0 if _print_find_results(result.devices, profiles, include_low_score=args.all) else 1


def cmd_info(args: argparse.Namespace) -> int:
    try:
        devices = devices_blocking(timeout=args.timeout)
    except BlueZUnavailable as exc:
        print(f"BlueZ info unavailable: {exc}", file=sys.stderr)
        return 2
    wanted = args.device.lower()
    for device in devices:
        if device.path == args.device or (device.address and device.address.lower() == wanted):
            _print_device(device)
            return 0
    print(f"Device not found: {args.device}", file=sys.stderr)
    return 1


def cmd_pair(args: argparse.Namespace) -> int:
    def progress(message: str) -> None:
        print(message, flush=True)

    try:
        device = pair_blocking(
            args.device,
            trust=not args.no_trust,
            connect=not args.no_connect,
            timeout=args.timeout,
            progress=progress,
        )
    except BlueZUnavailable as exc:
        print(f"BlueZ pairing unavailable: {exc}", file=sys.stderr)
        print("Manual bluetoothctl fallback:", file=sys.stderr)
        print(f"  bluetoothctl pair {args.device}", file=sys.stderr)
        if not args.no_trust:
            print(f"  bluetoothctl trust {args.device}", file=sys.stderr)
        if not args.no_connect:
            print(f"  bluetoothctl connect {args.device}", file=sys.stderr)
        return 2
    _print_device(device)
    return 0


def cmd_gatt(args: argparse.Namespace) -> int:
    try:
        objects = gatt_objects_blocking(args.device)
    except BlueZUnavailable as exc:
        print(f"BlueZ GATT inspection unavailable: {exc}", file=sys.stderr)
        return 2
    if not objects:
        print("No GATT objects found. Ensure the remote is connected.")
        return 1
    for item in objects:
        print(f"{item.kind}: {item.path}")
        print(f"  UUID: {item.uuid or '-'}")
        if item.flags:
            print(f"  Flags: {', '.join(item.flags)}")
        if item.service:
            print(f"  Service: {item.service}")
        if item.characteristic:
            print(f"  Characteristic: {item.characteristic}")
        if item.notifying is not None:
            print(f"  Notifying: {item.notifying}")
    return 0


def cmd_gatt_read(args: argparse.Namespace) -> int:
    try:
        path, value = read_gatt_blocking(args.device, args.target)
    except BlueZUnavailable as exc:
        print(f"BlueZ GATT read unavailable: {exc}", file=sys.stderr)
        return 2
    print(path)
    print(value.hex(" "))
    return 0


def cmd_gatt_write(args: argparse.Namespace) -> int:
    try:
        value = bytes.fromhex(args.hex_value)
    except ValueError:
        print(f"Invalid hex value: {args.hex_value}", file=sys.stderr)
        return 1
    try:
        path = write_gatt_blocking(args.device, args.target, value)
    except BlueZUnavailable as exc:
        print(f"BlueZ GATT write unavailable: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {value.hex(' ')} to {path}")
    return 0


def _print_gatt_value(path: str, value: bytes) -> None:
    classification = classify_button_payload(value)
    if classification is None and len(value) > 2:
        classification = classify_button_payload(value[-2:])
    fields = [f"{time.time():.3f}", f"path={path}", f"raw={value.hex()}", f"len={len(value)}"]
    if classification is not None:
        fields.extend(
            [
                "type=button",
                f"state={classification.state}",
                f"known={str(classification.known_value).lower()}",
                f'note="{classification.note}"',
            ]
        )
        if classification.action is not None:
            fields.append(f"action={classification.action.value}")
    else:
        fields.append("type=raw")
    print(" ".join(fields), flush=True)


async def _gatt_notify_async(args: argparse.Namespace) -> int:
    client = BlueZClient()
    for write_spec in args.write:
        if "=" not in write_spec:
            print(f"Invalid --write value, expected target=hex: {write_spec}", file=sys.stderr)
            return 1
        target, hex_value = write_spec.split("=", 1)
        try:
            value = bytes.fromhex(hex_value)
        except ValueError:
            print(f"Invalid --write hex value: {hex_value}", file=sys.stderr)
            return 1
        path = await client.write_gatt(args.device, target, value)
        print(f"wrote {value.hex(' ')} to {path}")

    queue = asyncio.Queue()
    notify_task = asyncio.create_task(client.notify_gatt(args.device, args.target, args.timeout, queue))
    print("monitoring GATT notifications")
    try:
        while True:
            if notify_task.done():
                await notify_task
                return 0
            try:
                notification = await asyncio.wait_for(queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            _print_gatt_value(notification.path, notification.value)
    except KeyboardInterrupt:
        print("stopped")
        return 130
    finally:
        notify_task.cancel()
        try:
            await notify_task
        except asyncio.CancelledError:
            pass


def cmd_gatt_notify(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_gatt_notify_async(args))
    except KeyboardInterrupt:
        print("stopped")
        return 130
    except BlueZUnavailable as exc:
        print(f"BlueZ GATT notify unavailable: {exc}", file=sys.stderr)
        return 2
    except PermissionError:
        print("Permission denied using BlueZ GATT. Try running this diagnostic with sudo.", file=sys.stderr)
        return 13


def cmd_hidraw(args: argparse.Namespace) -> int:
    devices = find_hidraw_devices(vendor_id=args.vendor_id, product_id=args.product_id)
    if not devices:
        print("No matching hidraw devices found.")
        return 1
    for device in devices:
        print(f"{device.name}: {device.dev_path}")
        print(f"  HID ID: {device.hid_id or '-'}")
        print(f"  Vendor/Product: {device.vendor_id or '-'}/{device.product_id or '-'}")
        print(f"  Name: {device.device_name or '-'}")
        print(f"  Unique identity: {device.uniq or '-'}")
        print(f"  Physical path: {device.phys or '-'}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    if args.hidraw:
        path = Path(args.hidraw)
    else:
        matches = find_hidraw_devices(vendor_id=args.vendor_id, product_id=args.product_id)
        if not matches:
            print("No matching hidraw device found. Pair/connect the remote first or pass --hidraw.", file=sys.stderr)
            return 1
        if len(matches) > 1:
            print("Multiple matching hidraw devices found; pass --hidraw explicitly:", file=sys.stderr)
            for match in matches:
                print(f"  {match.dev_path}", file=sys.stderr)
            return 1
        path = matches[0].dev_path
    try:
        return monitor_hidraw(path, output=sys.stdout, timeout=args.timeout)
    except FileNotFoundError:
        print(f"hidraw path does not exist: {path}. Use `kousen-remote hidraw` to list real paths.", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"Permission denied reading {path}. You may need udev permissions or sudo for diagnostics.", file=sys.stderr)
        return 13


def cmd_btmon_test(args: argparse.Namespace) -> int:
    try:
        return monitor_btmon(
            output=sys.stdout,
            timeout=args.timeout,
            btmon_path=args.btmon,
            buttons_only=args.buttons_only,
        )
    except FileNotFoundError:
        print("btmon was not found. Install the BlueZ diagnostic tools package on Debian.", file=sys.stderr)
        return 1
    except PermissionError:
        print("Permission denied running btmon. Run this command with sudo for diagnostics.", file=sys.stderr)
        return 13


def cmd_run(args: argparse.Namespace) -> int:
    mapping = load_mapping(args.mapping) if args.mapping else MappingConfig.default()
    return run_service(
        RuntimeConfig(
            device=args.device,
            button_characteristic=args.button_characteristic,
            output=args.output,
            mapping=mapping,
            timeout=args.timeout,
            reconnect=not args.no_reconnect,
            reconnect_delay=args.reconnect_delay,
            max_reconnect_delay=args.max_reconnect_delay,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kousen-remote")
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILE_DIR, help="device profile directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="scan for plausible compatible remotes")
    scan.add_argument("--seconds", type=float, default=8.0)
    scan.add_argument("--timeout", type=float, help="outer timeout for the BlueZ D-Bus scan")
    scan.add_argument("--all", action="store_true", help="show low-scoring devices too")
    scan.add_argument("--no-hid-filter", action="store_true", help="do not ask BlueZ to filter by HID UUID")
    scan.add_argument("--no-bluetoothctl-fallback", action="store_true", help="do not fall back when D-Bus scanning fails")
    scan.add_argument("--bluetoothctl", default="bluetoothctl", help="bluetoothctl executable path")
    scan.add_argument("--info-timeout", type=float, default=5.0, help="timeout for each bluetoothctl info call")
    scan.set_defaults(func=cmd_scan)

    find = subparsers.add_parser("find", help="find likely Siri Remote devices with bluetoothctl")
    find.add_argument("--seconds", type=float, default=30.0)
    find.add_argument("--all", action="store_true", help="show low-scoring devices too")
    find.add_argument("--no-hid-filter", action="store_true", help="do not configure the BLE HID UUID scan filter")
    find.add_argument("--bluetoothctl", default="bluetoothctl", help="bluetoothctl executable path")
    find.add_argument("--info-timeout", type=float, default=5.0, help="timeout for each bluetoothctl info call")
    find.set_defaults(func=cmd_find)

    devices = subparsers.add_parser("devices", help="list known BlueZ devices and candidate scores")
    devices.add_argument("--timeout", type=float, default=8.0, help="outer timeout for BlueZ D-Bus device listing")
    devices.add_argument("--all", action="store_true", help="show low-scoring devices too")
    devices.set_defaults(func=cmd_devices)

    info = subparsers.add_parser("info", help="show BlueZ metadata for one device")
    info.add_argument("device", help="Bluetooth address or BlueZ object path")
    info.add_argument("--timeout", type=float, default=8.0, help="outer timeout for BlueZ D-Bus device listing")
    info.set_defaults(func=cmd_info)

    pair = subparsers.add_parser("pair", help="pair, trust, and connect a BlueZ device")
    pair.add_argument("device", help="Bluetooth address or BlueZ object path")
    pair.add_argument("--timeout", type=float, default=30.0, help="timeout for each pair/trust/connect operation")
    pair.add_argument("--no-trust", action="store_true")
    pair.add_argument("--no-connect", action="store_true")
    pair.set_defaults(func=cmd_pair)

    gatt = subparsers.add_parser("gatt", help="inspect BlueZ GATT services, characteristics, and descriptors")
    gatt.add_argument("device", help="Bluetooth address or BlueZ object path")
    gatt.set_defaults(func=cmd_gatt)

    gatt_read = subparsers.add_parser("gatt-read", help="read a GATT characteristic or descriptor")
    gatt_read.add_argument("device", help="Bluetooth address or BlueZ object path")
    gatt_read.add_argument("target", help="full GATT object path or suffix such as char0038/desc003b")
    gatt_read.set_defaults(func=cmd_gatt_read)

    gatt_write = subparsers.add_parser("gatt-write", help="write hex bytes to a GATT characteristic")
    gatt_write.add_argument("device", help="Bluetooth address or BlueZ object path")
    gatt_write.add_argument("target", help="full GATT object path or suffix such as char004c")
    gatt_write.add_argument("hex_value", help="hex bytes, for example af or 0100")
    gatt_write.set_defaults(func=cmd_gatt_write)

    gatt_notify = subparsers.add_parser("gatt-notify", help="actively subscribe to one GATT characteristic")
    gatt_notify.add_argument("device", help="Bluetooth address or BlueZ object path")
    gatt_notify.add_argument("target", help="full GATT characteristic path or suffix such as char0038")
    gatt_notify.add_argument("--timeout", type=float)
    gatt_notify.add_argument(
        "--write",
        action="append",
        default=[],
        help="write before subscribing, as target=hex; may be repeated",
    )
    gatt_notify.set_defaults(func=cmd_gatt_notify)

    hidraw = subparsers.add_parser("hidraw", help="inspect matching Linux hidraw devices")
    hidraw.add_argument("--vendor-id", default="004c")
    hidraw.add_argument("--product-id", default="0315")
    hidraw.set_defaults(func=cmd_hidraw)

    test = subparsers.add_parser("test", help="print raw hidraw reports for diagnostic comparison")
    test.add_argument("--hidraw", help="explicit /dev/hidrawN path")
    test.add_argument("--vendor-id", default="004c")
    test.add_argument("--product-id", default="0315")
    test.add_argument("--timeout", type=float)
    test.set_defaults(func=cmd_test)

    btmon_test = subparsers.add_parser("btmon-test", help="parse btmon ATT notifications for diagnostics")
    btmon_test.add_argument("--timeout", type=float)
    btmon_test.add_argument("--btmon", default="btmon", help="btmon executable path")
    btmon_test.add_argument("--buttons-only", action="store_true", help="suppress touch/vendor diagnostic reports")
    btmon_test.set_defaults(func=cmd_btmon_test)

    run = subparsers.add_parser("run", help="run the daemon runtime")
    run.add_argument("device", help="Bluetooth address or BlueZ object path")
    run.add_argument("--button-characteristic", default=DEFAULT_BUTTON_CHARACTERISTIC)
    run.add_argument("--mapping", type=Path, help="JSON mapping config")
    run.add_argument("--output", choices=["uinput", "print"], default="uinput")
    run.add_argument("--timeout", type=float)
    run.add_argument("--no-reconnect", action="store_true", help="exit instead of retrying when the remote is unavailable")
    run.add_argument("--reconnect-delay", type=float, default=2.0, help="initial reconnect retry delay in seconds")
    run.add_argument("--max-reconnect-delay", type=float, default=30.0, help="maximum reconnect retry delay in seconds")
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
