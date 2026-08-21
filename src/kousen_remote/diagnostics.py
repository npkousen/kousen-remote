from __future__ import annotations

import os
import selectors
import time
from pathlib import Path
from typing import TextIO

from .drivers.apple_siri_remote_3 import classify_button_payload


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
            events = selector.select(remaining)
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
