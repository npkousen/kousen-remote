from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kousen_remote.devices import find_hidraw_devices
from kousen_remote.diagnostics import monitor_hidraw
from kousen_remote.discovery.bluez import BlueZUnavailable, devices_blocking, pair_blocking, scan_blocking
from kousen_remote.discovery.scoring import rank_candidates
from kousen_remote.model import DeviceRecord
from kousen_remote.profiles import DeviceProfile, load_profiles
from kousen_remote.service.runtime import run_service


DEFAULT_PROFILE_DIR = Path("profiles")


def _load_profiles_or_exit(path: Path) -> list[DeviceProfile]:
    profiles = load_profiles(path)
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


def cmd_scan(args: argparse.Namespace) -> int:
    profiles = _load_profiles_or_exit(args.profiles)
    try:
        devices = scan_blocking(args.seconds, hid_only=not args.no_hid_filter)
    except BlueZUnavailable as exc:
        print(f"BlueZ scan unavailable: {exc}", file=sys.stderr)
        return 2
    _print_candidates(devices, profiles, include_low_score=args.all)
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    profiles = _load_profiles_or_exit(args.profiles)
    try:
        devices = devices_blocking()
    except BlueZUnavailable as exc:
        print(f"BlueZ devices unavailable: {exc}", file=sys.stderr)
        return 2
    _print_candidates(devices, profiles, include_low_score=args.all)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    try:
        devices = devices_blocking()
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
    try:
        device = pair_blocking(args.device, trust=not args.no_trust, connect=not args.no_connect)
    except BlueZUnavailable as exc:
        print(f"BlueZ pairing unavailable: {exc}", file=sys.stderr)
        return 2
    _print_device(device)
    return 0


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
    except PermissionError:
        print(f"Permission denied reading {path}. You may need udev permissions or sudo for diagnostics.", file=sys.stderr)
        return 13


def cmd_run(_args: argparse.Namespace) -> int:
    try:
        return run_service()
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kousen-remote")
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILE_DIR, help="device profile directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="scan for plausible compatible remotes")
    scan.add_argument("--seconds", type=float, default=8.0)
    scan.add_argument("--all", action="store_true", help="show low-scoring devices too")
    scan.add_argument("--no-hid-filter", action="store_true", help="do not ask BlueZ to filter by HID UUID")
    scan.set_defaults(func=cmd_scan)

    devices = subparsers.add_parser("devices", help="list known BlueZ devices and candidate scores")
    devices.add_argument("--all", action="store_true", help="show low-scoring devices too")
    devices.set_defaults(func=cmd_devices)

    info = subparsers.add_parser("info", help="show BlueZ metadata for one device")
    info.add_argument("device", help="Bluetooth address or BlueZ object path")
    info.set_defaults(func=cmd_info)

    pair = subparsers.add_parser("pair", help="pair, trust, and connect a BlueZ device")
    pair.add_argument("device", help="Bluetooth address or BlueZ object path")
    pair.add_argument("--no-trust", action="store_true")
    pair.add_argument("--no-connect", action="store_true")
    pair.set_defaults(func=cmd_pair)

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

    run = subparsers.add_parser("run", help="run the daemon runtime (planned for Milestone 2)")
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
