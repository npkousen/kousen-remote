from __future__ import annotations

from typing import Protocol


class KeyOutput(Protocol):
    def press_key(self, key_code: str) -> None:
        ...

    def release_key(self, key_code: str) -> None:
        ...

    def close(self) -> None:
        ...
