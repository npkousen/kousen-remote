from __future__ import annotations

from enum import Enum


class NormalizedAction(str, Enum):
    NAV_UP = "NAV_UP"
    NAV_DOWN = "NAV_DOWN"
    NAV_LEFT = "NAV_LEFT"
    NAV_RIGHT = "NAV_RIGHT"
    SELECT = "SELECT"
    BACK = "BACK"
    HOME = "HOME"
    PLAY_PAUSE = "PLAY_PAUSE"
    VOLUME_UP = "VOLUME_UP"
    VOLUME_DOWN = "VOLUME_DOWN"
    MUTE = "MUTE"
    POWER = "POWER"


class RichEventType(str, Enum):
    TOUCH_START = "TOUCH_START"
    TOUCH_MOVE = "TOUCH_MOVE"
    TOUCH_END = "TOUCH_END"
    SWIPE_UP = "SWIPE_UP"
    SWIPE_DOWN = "SWIPE_DOWN"
    SWIPE_LEFT = "SWIPE_LEFT"
    SWIPE_RIGHT = "SWIPE_RIGHT"
    SCROLL = "SCROLL"
    LONG_PRESS = "LONG_PRESS"
