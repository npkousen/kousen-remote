from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import TextIO

from kousen_remote.discovery.bluez import BlueZClient, BlueZUnavailable
from kousen_remote.drivers.apple_siri_remote_3 import classify_button_payload
from kousen_remote.mapping import MappingConfig, NormalizedAction
from kousen_remote.outputs import KeyOutput
from kousen_remote.outputs.uinput import EvdevUnavailable, PrintKeyOutput, UInputKeyboard


DEFAULT_BUTTON_CHARACTERISTIC = "char0038"


@dataclass(frozen=True)
class RuntimeConfig:
    device: str
    button_characteristic: str = DEFAULT_BUTTON_CHARACTERISTIC
    output: str = "uinput"
    mapping: MappingConfig | None = None
    timeout: float | None = None
    reconnect: bool = True
    reconnect_delay: float = 2.0
    max_reconnect_delay: float = 30.0
    connect_before_subscribe: bool = True


class ActionDispatcher:
    def __init__(self, *, mapping: MappingConfig, output: KeyOutput, stream: TextIO | None = None) -> None:
        self.mapping = mapping
        self.output = output
        self.stream = stream or sys.stdout
        self._active_action: NormalizedAction | None = None
        self._active_key: str | None = None

    @property
    def active_action(self) -> NormalizedAction | None:
        return self._active_action

    def handle_payload(self, payload: bytes) -> None:
        report = classify_button_payload(payload)
        if report is None:
            return
        if report.state == "release":
            self.release_active()
            return
        if report.action is None:
            print(f"ignored raw={report.raw} reason=unmapped", file=self.stream, flush=True)
            return
        self.press_action(report.action, raw=report.raw)

    def press_action(self, action: NormalizedAction, *, raw: str) -> None:
        key_code = self.mapping.key_for(action)
        if key_code is None:
            print(f"ignored action={action.value} raw={raw} reason=no-key-mapping", file=self.stream, flush=True)
            return
        if self._active_key == key_code:
            return
        self.release_active()
        self.output.press_key(key_code)
        self._active_action = action
        self._active_key = key_code
        print(f"action={action.value} key={key_code} state=press raw={raw}", file=self.stream, flush=True)

    def release_active(self) -> None:
        if self._active_key is None:
            return
        key_code = self._active_key
        action = self._active_action
        self.output.release_key(key_code)
        print(f"action={action.value if action else '-'} key={key_code} state=release", file=self.stream, flush=True)
        self._active_action = None
        self._active_key = None

    def close(self) -> None:
        self.release_active()
        self.output.close()


def create_output(name: str) -> KeyOutput:
    if name == "print":
        return PrintKeyOutput()
    if name == "uinput":
        return UInputKeyboard()
    raise ValueError(f"Unknown output: {name}")


def _remaining_timeout(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


async def _run_notification_session(
    *,
    client: BlueZClient,
    dispatcher: ActionDispatcher,
    config: RuntimeConfig,
    session_timeout: float | None,
) -> None:
    queue = asyncio.Queue()
    notify_task = asyncio.create_task(
        client.notify_gatt(config.device, config.button_characteristic, session_timeout, queue)
    )
    print(
        f"kousen-remote subscribed device={config.device} characteristic={config.button_characteristic}",
        flush=True,
    )
    try:
        while True:
            if notify_task.done():
                await notify_task
                return
            try:
                notification = await asyncio.wait_for(queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            dispatcher.handle_payload(notification.value)
    finally:
        notify_task.cancel()
        try:
            await notify_task
        except asyncio.CancelledError:
            pass


async def run_service_async(config: RuntimeConfig) -> int:
    mapping = config.mapping or MappingConfig.default()
    output = create_output(config.output)
    dispatcher = ActionDispatcher(mapping=mapping, output=output)
    client = BlueZClient()
    deadline = time.monotonic() + config.timeout if config.timeout is not None else None
    attempt = 0
    print(
        f"kousen-remote listening device={config.device} characteristic={config.button_characteristic} "
        f"output={config.output} reconnect={str(config.reconnect).lower()}",
        flush=True,
    )
    try:
        while True:
            remaining = _remaining_timeout(deadline)
            if remaining == 0.0:
                return 0
            try:
                if config.connect_before_subscribe:
                    await client.connect_device(config.device)
                await _run_notification_session(
                    client=client,
                    dispatcher=dispatcher,
                    config=config,
                    session_timeout=remaining,
                )
                return 0
            except BlueZUnavailable as exc:
                dispatcher.release_active()
                if not config.reconnect:
                    raise
                attempt += 1
                delay = min(config.max_reconnect_delay, config.reconnect_delay * min(attempt, 8))
                remaining = _remaining_timeout(deadline)
                if remaining == 0.0:
                    return 0
                if remaining is not None:
                    delay = min(delay, remaining)
                print(f"remote unavailable: {exc}; retrying in {delay:.1f}s", flush=True)
                await asyncio.sleep(delay)
                continue
    finally:
        dispatcher.close()


def run_service(config: RuntimeConfig) -> int:
    try:
        return asyncio.run(run_service_async(config))
    except KeyboardInterrupt:
        print("stopped")
        return 130
    except BlueZUnavailable as exc:
        print(f"BlueZ runtime unavailable: {exc}", file=sys.stderr)
        return 2
    except EvdevUnavailable as exc:
        print(f"uinput output unavailable: {exc}", file=sys.stderr)
        return 3
