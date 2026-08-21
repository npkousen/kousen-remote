from __future__ import annotations

import os
import re
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .drivers.apple_siri_remote_3 import classify_button_payload


HANDLE_RE = re.compile(r"\bHandle:\s*(0x[0-9a-fA-F]+)")
DATA_RE = re.compile(r"\bData(?:\[\d+\])?:\s*([0-9a-fA-F ]+)")


@dataclass(frozen=True)
class BtmonEvent:
    handle: str | None
    raw: str
    kind: str
    state: str | None = None
    known: bool | None = None
    note: str | None = None


class BtmonParser:
    def __init__(self) -> None:
        self._last_handle: str | None = None

    def parse_line(self, line: str) -> BtmonEvent | None:
        handle_match = HANDLE_RE.search(line)
        if handle_match:
            self._last_handle = handle_match.group(1).lower()

        data_match = DATA_RE.search(line)
        if not data_match:
            return None

        raw = "".join(data_match.group(1).split()).lower()
        if not raw:
            return None
        try:
            payload = bytes.fromhex(raw)
        except ValueError:
            return None

        classification = classify_button_payload(payload)
        if classification is not None:
            return BtmonEvent(
                handle=self._last_handle,
                raw=raw,
                kind="button",
                state=classification.state,
                known=classification.known_value,
                note=classification.note,
            )
        if len(payload) == 11:
            return BtmonEvent(
                handle=self._last_handle,
                raw=raw,
                kind="touch",
                note="observed 11-byte touch-sized payload; schema not decoded",
            )
        if len(payload) == 99:
            return BtmonEvent(
                handle=self._last_handle,
                raw=raw,
                kind="vendor-large",
                note="observed 99-byte vendor-sized payload; schema not decoded",
            )
        return BtmonEvent(handle=self._last_handle, raw=raw, kind="raw", note=f"{len(payload)} byte payload")


def _print_btmon_event(event: BtmonEvent, output: TextIO) -> None:
    fields = [
        f"{time.time():.3f}",
        f"handle={event.handle or '-'}",
        f"raw={event.raw}",
        f"type={event.kind}",
    ]
    if event.state is not None:
        fields.append(f"state={event.state}")
    if event.known is not None:
        fields.append(f"known={str(event.known).lower()}")
    if event.note is not None:
        fields.append(f'note="{event.note}"')
    print(" ".join(fields), file=output, flush=True)


def monitor_hidraw(path: Path, *, output: TextIO, timeout: float | None = None) -> int:
    started = time.monotonic()
    selector = selectors.DefaultSelector()
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        selector.register(fd, selectors.EVENT_READ)
        print(f"monitoring {path}", file=output)
        while True:
            remaining = None
            if timeout is not None:
                elapsed = time.monotonic() - started
                remaining = max(0.0, timeout - elapsed)
                if remaining == 0.0:
                    return 0
            try:
                events = selector.select(remaining)
            except KeyboardInterrupt:
                print("stopped", file=output)
                return 130
            if not events:
                return 0
            for key, _mask in events:
                try:
                    payload = os.read(key.fd, 256)
                except BlockingIOError:
                    continue
                if not payload:
                    continue
                classification = classify_button_payload(payload)
                if classification is None and len(payload) > 2:
                    # hidraw reports may include a report id before the two-byte button state.
                    classification = classify_button_payload(payload[-2:])
                if classification is None:
                    print(f"{time.time():.3f} raw={payload.hex()} type=raw len={len(payload)}", file=output)
                else:
                    print(
                        f"{time.time():.3f} raw={payload.hex()} "
                        f"type=button state={classification.state} "
                        f"value={classification.raw} known={str(classification.known_value).lower()} "
                        f"note=\"{classification.note}\"",
                        file=output,
                    )
    finally:
        selector.close()
        os.close(fd)


def monitor_btmon(
    *,
    output: TextIO,
    timeout: float | None = None,
    btmon_path: str = "btmon",
    buttons_only: bool = False,
) -> int:
    started = time.monotonic()
    parser = BtmonParser()
    process = subprocess.Popen(
        [btmon_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        process.terminate()
        return 1

    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        print(f"monitoring {btmon_path}", file=output, flush=True)
        while True:
            if process.poll() is not None:
                return process.returncode or 0
            remaining = None
            if timeout is not None:
                elapsed = time.monotonic() - started
                remaining = max(0.0, timeout - elapsed)
                if remaining == 0.0:
                    return 0
            try:
                events = selector.select(remaining)
            except KeyboardInterrupt:
                print("stopped", file=output)
                return 130
            if not events:
                return 0
            for key, _mask in events:
                line = key.fileobj.readline()
                if not line:
                    continue
                event = parser.parse_line(line)
                if event is not None:
                    if buttons_only and event.kind != "button":
                        continue
                    _print_btmon_event(event, output)
    finally:
        selector.close()
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
