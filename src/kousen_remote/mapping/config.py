from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .actions import NormalizedAction


DEFAULT_KEY_MAPPING: dict[NormalizedAction, str] = {
    NormalizedAction.NAV_UP: "KEY_UP",
    NormalizedAction.NAV_DOWN: "KEY_DOWN",
    NormalizedAction.NAV_LEFT: "KEY_LEFT",
    NormalizedAction.NAV_RIGHT: "KEY_RIGHT",
    NormalizedAction.SELECT: "KEY_ENTER",
    NormalizedAction.BACK: "KEY_ESC",
    NormalizedAction.HOME: "KEY_HOME",
    NormalizedAction.PLAY_PAUSE: "KEY_SPACE",
    NormalizedAction.VOLUME_UP: "KEY_VOLUMEUP",
    NormalizedAction.VOLUME_DOWN: "KEY_VOLUMEDOWN",
    NormalizedAction.MUTE: "KEY_MUTE",
    NormalizedAction.SIRI: "KEY_F13",
}


@dataclass(frozen=True)
class MappingConfig:
    name: str
    actions_to_keys: dict[NormalizedAction, str]

    @classmethod
    def default(cls) -> "MappingConfig":
        return cls(name="default", actions_to_keys=dict(DEFAULT_KEY_MAPPING))

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MappingConfig":
        raw_mapping = data.get("actions_to_keys", {})
        if not isinstance(raw_mapping, dict):
            raise ValueError("actions_to_keys must be an object")
        parsed: dict[NormalizedAction, str] = {}
        for action, key_code in raw_mapping.items():
            parsed[NormalizedAction(str(action))] = str(key_code)
        return cls(name=str(data.get("name", "custom")), actions_to_keys=parsed)

    def key_for(self, action: NormalizedAction) -> str | None:
        return self.actions_to_keys.get(action)


def load_mapping(path: Path) -> MappingConfig:
    with path.open("r", encoding="utf-8") as handle:
        return MappingConfig.from_dict(json.load(handle))
