from __future__ import annotations

from dataclasses import dataclass


KNOWN_BUTTON_VALUES = frozenset(
    {
        "0100",
        "0200",
        "0400",
        "1000",
        "2000",
        "4000",
        "8000",
        "0001",
    }
)
RELEASE_VALUE = "0000"


@dataclass(frozen=True)
class ButtonReport:
    raw: str
    state: str
    known_value: bool
    note: str


def classify_button_payload(payload: bytes) -> ButtonReport | None:
    """Classify the observed two-byte Apple button stream without assigning labels."""
    if len(payload) != 2:
        return None
    raw = payload.hex()
    if raw == RELEASE_VALUE:
        return ButtonReport(raw=raw, state="release", known_value=True, note="observed neutral/release")
    if raw in KNOWN_BUTTON_VALUES:
        return ButtonReport(
            raw=raw,
            state="press",
            known_value=True,
            note="known raw button value; semantic label not established",
        )
    return ButtonReport(raw=raw, state="press", known_value=False, note="unrecognized two-byte button payload")
