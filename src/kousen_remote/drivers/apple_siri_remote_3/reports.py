from __future__ import annotations

from dataclasses import dataclass

from kousen_remote.mapping import NormalizedAction


KNOWN_BUTTON_VALUES = frozenset(
    {
        "0001",
        "0002",
        "0004",
        "0008",
        "0010",
        "0100",
        "0200",
        "0400",
        "0800",
        "1000",
        "2000",
        "4000",
        "8000",
    }
)
RELEASE_VALUE = "0000"

LABELED_BUTTON_ACTIONS: dict[str, NormalizedAction] = {
    "0002": NormalizedAction.NAV_UP,
    "0008": NormalizedAction.NAV_DOWN,
    "0010": NormalizedAction.NAV_LEFT,
    "0004": NormalizedAction.NAV_RIGHT,
    "0800": NormalizedAction.SELECT,
    "4000": NormalizedAction.BACK,
    "0100": NormalizedAction.HOME,
    "0001": NormalizedAction.PLAY_PAUSE,
    "8000": NormalizedAction.MUTE,
    "0200": NormalizedAction.VOLUME_UP,
    "0400": NormalizedAction.VOLUME_DOWN,
    "1000": NormalizedAction.POWER,
    "2000": NormalizedAction.SIRI,
}


@dataclass(frozen=True)
class ButtonReport:
    raw: str
    state: str
    known_value: bool
    note: str
    action: NormalizedAction | None = None


def classify_button_payload(payload: bytes) -> ButtonReport | None:
    """Classify the observed two-byte Apple button stream without assigning labels."""
    if len(payload) != 2:
        return None
    raw = payload.hex()
    if raw == RELEASE_VALUE:
        return ButtonReport(raw=raw, state="release", known_value=True, note="observed neutral/release")
    action = LABELED_BUTTON_ACTIONS.get(raw)
    if action is not None:
        return ButtonReport(
            raw=raw,
            state="press",
            known_value=True,
            note="labeled from active GATT capture on Remote #1",
            action=action,
        )
    if raw in KNOWN_BUTTON_VALUES:
        return ButtonReport(
            raw=raw,
            state="press",
            known_value=True,
            note="known raw button value; semantic label not established",
        )
    return ButtonReport(raw=raw, state="press", known_value=False, note="unrecognized two-byte button payload")
