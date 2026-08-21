from __future__ import annotations

import sys
from typing import TextIO


class EvdevUnavailable(RuntimeError):
    pass


class PrintKeyOutput:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def press_key(self, key_code: str) -> None:
        print(f"press {key_code}", file=self.stream, flush=True)

    def release_key(self, key_code: str) -> None:
        print(f"release {key_code}", file=self.stream, flush=True)

    def close(self) -> None:
        pass


class UInputKeyboard:
    def __init__(self, *, name: str = "kousen-remote") -> None:
        try:
            from evdev import UInput, ecodes
        except ImportError as exc:
            raise EvdevUnavailable(
                "python-evdev is required for uinput output. On Debian, install python3-evdev "
                "or install the package dependencies, then use a --system-site-packages venv."
            ) from exc

        self._ecodes = ecodes
        self._known_keys = self._build_key_set()
        capabilities = {ecodes.EV_KEY: sorted(self._known_keys)}
        try:
            self._device = UInput(capabilities, name=name)
        except PermissionError as exc:
            raise EvdevUnavailable(
                "permission denied opening /dev/uinput. Run with sudo for testing or add reviewed udev/group rules."
            ) from exc

    def _build_key_set(self) -> set[int]:
        key_names = {
            "KEY_UP",
            "KEY_DOWN",
            "KEY_LEFT",
            "KEY_RIGHT",
            "KEY_ENTER",
            "KEY_ESC",
            "KEY_HOME",
            "KEY_SPACE",
            "KEY_PLAYPAUSE",
            "KEY_VOLUMEUP",
            "KEY_VOLUMEDOWN",
            "KEY_MUTE",
            "KEY_POWER",
            "KEY_F13",
        }
        return {self._resolve_key(name) for name in key_names if hasattr(self._ecodes, name)}

    def _resolve_key(self, key_code: str) -> int:
        if not hasattr(self._ecodes, key_code):
            raise EvdevUnavailable(f"Unsupported evdev key code: {key_code}")
        value = getattr(self._ecodes, key_code)
        if not isinstance(value, int):
            raise EvdevUnavailable(f"Unsupported evdev key code: {key_code}")
        return value

    def press_key(self, key_code: str) -> None:
        code = self._resolve_key(key_code)
        self._device.write(self._ecodes.EV_KEY, code, 1)
        self._device.syn()

    def release_key(self, key_code: str) -> None:
        code = self._resolve_key(key_code)
        self._device.write(self._ecodes.EV_KEY, code, 0)
        self._device.syn()

    def close(self) -> None:
        self._device.close()
