from __future__ import annotations

import os
import re
import select
import subprocess
import time
from dataclasses import dataclass
from shutil import which
from typing import BinaryIO

from kousen_remote.model import HID_SERVICE_UUID, DeviceRecord, normalize_uuid


DEVICE_EVENT_RE = re.compile(r"\[(?:NEW|CHG)\]\s+Device\s+([0-9A-Fa-f:]{17})\b")
DEVICE_INFO_RE = re.compile(r"\bDevice\s+([0-9A-Fa-f:]{17})\b")
UUID_RE = re.compile(r"\(([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)")
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class BluetoothCtlUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class BluetoothCtlScanResult:
    devices: list[DeviceRecord]
    raw_output: str


def _clean_line(line: str) -> str:
    cleaned = ANSI_RE.sub("", line).strip()
    if "]#" in cleaned:
        cleaned = cleaned.split("]#", 1)[1].strip()
    return cleaned


def discovered_addresses(output: str) -> list[str]:
    addresses: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        match = DEVICE_EVENT_RE.search(_clean_line(line))
        if match is not None:
            address = match.group(1).upper()
            if address not in seen:
                seen.add(address)
                addresses.append(address)
    return addresses


def parse_info(output: str, *, address: str | None = None) -> DeviceRecord:
    manufacturer_data: dict[int, bytes] = {}
    uuids: list[str] = []
    current_manufacturer_key: int | None = None
    pending_manufacturer_value = False

    parsed_address = address
    name: str | None = None
    alias: str | None = None
    address_type: str | None = None
    appearance: int | None = None
    modalias: str | None = None
    rssi: int | None = None
    paired: bool | None = None
    bonded: bool | None = None
    trusted: bool | None = None
    connected: bool | None = None

    def parse_bool(value: str) -> bool | None:
        lowered = value.strip().lower()
        if lowered in {"yes", "true"}:
            return True
        if lowered in {"no", "false"}:
            return False
        return None

    def parse_hex_bytes(value: str) -> bytes | None:
        hex_parts: list[str] = []
        for part in value.strip().split():
            if not re.fullmatch(r"[0-9a-fA-F]{2}", part):
                break
            hex_parts.append(part)
        if not hex_parts:
            return None
        return bytes(int(part, 16) for part in hex_parts)

    for raw_line in output.splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue

        if pending_manufacturer_value and current_manufacturer_key is not None:
            value = parse_hex_bytes(line)
            if value is not None:
                previous = manufacturer_data.get(current_manufacturer_key, b"")
                manufacturer_data[current_manufacturer_key] = previous + value
                continue
            pending_manufacturer_value = False

        device_match = DEVICE_INFO_RE.search(line)
        if device_match is not None:
            parsed_address = device_match.group(1).upper()
            type_match = re.search(r"\((public|random)\)", line, flags=re.IGNORECASE)
            if type_match is not None:
                address_type = type_match.group(1).lower()
            continue

        if ":" not in line:
            continue

        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower().replace(".", " ")
        if key == "name":
            name = value
        elif key == "alias":
            alias = value
        elif key in {"address type", "addresstype"}:
            address_type = value
        elif key == "appearance":
            appearance = int(value.split()[0], 16)
        elif key == "modalias":
            modalias = value
        elif key == "rssi":
            try:
                rssi = int(value.split()[0])
            except (IndexError, ValueError):
                rssi = None
        elif key == "paired":
            paired = parse_bool(value)
        elif key == "bonded":
            bonded = parse_bool(value)
        elif key == "trusted":
            trusted = parse_bool(value)
        elif key == "connected":
            connected = parse_bool(value)
        elif key == "uuid":
            uuid_match = UUID_RE.search(value)
            uuids.append(normalize_uuid(uuid_match.group(1) if uuid_match else value))
        elif key == "manufacturerdata key":
            current_manufacturer_key = int(value.split()[0], 16)
        elif key == "manufacturerdata value" and current_manufacturer_key is not None:
            parsed_value = parse_hex_bytes(value)
            if parsed_value is None:
                pending_manufacturer_value = True
            else:
                manufacturer_data[current_manufacturer_key] = parsed_value

    return DeviceRecord(
        address=parsed_address.upper() if parsed_address else None,
        address_type=address_type,
        name=name,
        alias=alias,
        uuids=tuple(dict.fromkeys(uuids)),
        manufacturer_data=manufacturer_data,
        appearance=appearance,
        modalias=modalias,
        rssi=rssi,
        paired=paired,
        bonded=bonded,
        trusted=trusted,
        connected=connected,
    )


def _write_command(stdin: BinaryIO | None, command: str) -> None:
    if stdin is None:
        raise BluetoothCtlUnavailable("bluetoothctl stdin is unavailable.")
    try:
        stdin.write(command.encode("utf-8") + b"\n")
        stdin.flush()
    except BrokenPipeError as exc:
        raise BluetoothCtlUnavailable("bluetoothctl exited before discovery commands could complete.") from exc


def scan_addresses(
    seconds: float,
    *,
    hid_only: bool = True,
    bluetoothctl_path: str = "bluetoothctl",
) -> tuple[list[str], str]:
    if which(bluetoothctl_path) is None:
        raise BluetoothCtlUnavailable("bluetoothctl was not found. Install the BlueZ command-line tools.")

    try:
        process = subprocess.Popen(
            [bluetoothctl_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        raise BluetoothCtlUnavailable(f"Could not start bluetoothctl: {exc}") from exc

    output: list[bytes] = []
    try:
        stdout_fd: int | None = None
        if process.stdout is not None:
            stdout_fd = process.stdout.fileno()
            os.set_blocking(stdout_fd, False)

        _write_command(process.stdin, "power on")
        _write_command(process.stdin, "pairable on")
        _write_command(process.stdin, "menu scan")
        _write_command(process.stdin, "transport le")
        if hid_only:
            _write_command(process.stdin, f"uuids {HID_SERVICE_UUID}")
        _write_command(process.stdin, "back")
        _write_command(process.stdin, "scan on")

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.stdout is None or stdout_fd is None:
                break
            ready, _write_ready, _error_ready = select.select([process.stdout], [], [], 0.25)
            if ready:
                try:
                    chunk = os.read(stdout_fd, 4096)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                output.append(chunk)
            if process.poll() is not None:
                break

        if stdout_fd is not None:
            os.set_blocking(stdout_fd, True)
        _write_command(process.stdin, "scan off")
        _write_command(process.stdin, "quit")
        try:
            remaining, _stderr = process.communicate(timeout=3)
            if remaining:
                output.append(remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            remaining, _stderr = process.communicate()
            if remaining:
                output.append(remaining)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()

    raw_output = b"".join(output).decode("utf-8", errors="replace")
    return discovered_addresses(raw_output), raw_output


def info(address: str, *, bluetoothctl_path: str = "bluetoothctl", timeout: float = 5.0) -> DeviceRecord:
    if which(bluetoothctl_path) is None:
        raise BluetoothCtlUnavailable("bluetoothctl was not found. Install the BlueZ command-line tools.")
    try:
        result = subprocess.run(
            [bluetoothctl_path, "info", address],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BluetoothCtlUnavailable(f"bluetoothctl info {address} timed out after {timeout:g} seconds.") from exc
    output = result.stdout + result.stderr
    if result.returncode != 0 and "Device" not in output:
        raise BluetoothCtlUnavailable(f"bluetoothctl info {address} failed: {output.strip()}")
    return parse_info(output, address=address)


def find_blocking(
    seconds: float,
    *,
    hid_only: bool = True,
    bluetoothctl_path: str = "bluetoothctl",
    info_timeout: float = 5.0,
) -> BluetoothCtlScanResult:
    addresses, raw_output = scan_addresses(seconds, hid_only=hid_only, bluetoothctl_path=bluetoothctl_path)
    devices: list[DeviceRecord] = []
    for address in addresses:
        try:
            devices.append(info(address, bluetoothctl_path=bluetoothctl_path, timeout=info_timeout))
        except BluetoothCtlUnavailable:
            devices.append(DeviceRecord(address=address))
    return BluetoothCtlScanResult(devices=devices, raw_output=raw_output)
