# development notes and roadmap

These notes capture the important observations from the first working Siri Remote integration. They are intended as a starting point for future `kousen-remote` work.

## Key observations

The Apple Siri Remote 3rd generation USB-C model is viable as a Linux input device on Debian through BlueZ.

The useful stable model signals are:

```text
Apple manufacturer ID: 0x004c
Product ID:            0315
Modalias:              bluetooth:v004Cp0315d0001
HID service:           00001812-0000-1000-8000-00805f9b34fb
Appearance:            0x03c0
```

The physical Bluetooth address identifies one remote, not the model. Device profiles should match model/family properties; paired device records should track physical addresses separately.

Passive diagnostics are useful, but runtime input should use active BlueZ GATT notification subscription. The reliable button path observed so far is:

```text
BlueZ device
  -> HID service
  -> Report characteristic suffix char0038
  -> two-byte button reports
  -> normalized action
  -> mapping profile
  -> uinput key
```

`hidraw` is useful for identity inspection, but it did not produce readable input reports in testing. `btmon` was useful for reverse engineering, but it should remain a diagnostic fallback rather than the daemon runtime.

## Labeled button map

Remote #1 produced this active-GATT button map:

```text
0002 -> NAV_UP
0008 -> NAV_DOWN
0010 -> NAV_LEFT
0004 -> NAV_RIGHT
0800 -> SELECT
4000 -> BACK
0100 -> HOME
0001 -> PLAY_PAUSE
8000 -> MUTE
0200 -> VOLUME_UP
0400 -> VOLUME_DOWN
1000 -> POWER
2000 -> SIRI
0000 -> release
```

Validate this with another same-generation remote before assuming it is universal across all firmware revisions, but it is expected to be portable for the same `004C:0315` profile.

## Runtime design lessons

- Keep `kousen-remote` standalone. KousenTV and Command Center should not contain Apple Bluetooth code.
- Prefer normalized actions over raw protocol values. Raw bytes should stay inside hardware drivers and diagnostics.
- Prefer Linux uinput as the primary output so browsers and media apps receive normal input.
- Keep web/API integrations secondary. A future web UI can manage/test remotes, but the remote should work when the UI is closed.
- Treat system effects carefully. Keys such as `KEY_POWER` can trigger OS-level behavior immediately.
- Use safe defaults. `POWER` is decoded but intentionally unmapped in the kiosk/browser profile.
- Keep `--output print` available. It is the fastest safe way to test a live remote over SSH.
- Keep reconnect behavior in the daemon. A sleeping Bluetooth remote should not require restarting the service.

## Power button strategy

The remote Power button currently decodes to normalized `POWER`, but the default kiosk/browser mapping does not emit a Linux key.

Do not map `POWER` to `KEY_POWER` by default. Linux treats `KEY_POWER` like a hardware power button, and it can shut down or suspend the host.

For future remapping, there are three reasonable approaches:

1. Map `POWER` to an inert high function key, such as `KEY_F14`, and let a focused app decide what to do.
2. Add an explicit local system-action output backend, such as `DISPLAY_SLEEP`, with an allowlist of supported commands.
3. Let Command Center write/update the `kousen-remote` mapping profile, then restart/reload the service.

For display sleep specifically, the cleanest long-term design is probably a local system action owned by the kiosk layer, not a raw `KEY_POWER` event. Examples could include:

```text
POWER -> DISPLAY_SLEEP
SIRI  -> OPEN_VOICE_OR_SEARCH
HOME  -> OPEN_COMMAND_CENTER_OR_HOME
```

That would require extending the mapping model beyond `action -> key_code` to support output targets such as:

```json
{
  "POWER": { "type": "system_action", "name": "DISPLAY_SLEEP" },
  "SIRI": { "type": "key", "code": "KEY_F13" }
}
```

Any command-backed system actions should be explicit, allowlisted, and documented. Avoid a generic "run arbitrary shell command from config" feature.

## Kousen control mapping

Because the Kousen stack controls the kiosk service, Command Center, and KousenTV, it can use a dedicated high-function-key input contract instead of general browser/media defaults.

Linux evdev standard function keys generally run through:

```text
KEY_F1 ... KEY_F24
```

There is no portable `KEY_F25`. For that reason, `mappings/kousen-control.json` uses `KEY_F13` through `KEY_F24` for twelve remappable controls and reserves Siri/Mic for `KEY_HOME`, which the kiosk can use as a safe global return-home action.

This gives KousenTV and Command Center a clean app-level contract:

```text
UP         -> F13
RIGHT      -> F14
DOWN       -> F15
LEFT       -> F16
SELECT     -> F17
BACK       -> F18
HOME       -> F19
PLAY_PAUSE -> F20
MUTE       -> F21
VOLUME_UP  -> F22
VOLUME_DOWN-> F23
POWER      -> F24
SIRI       -> Home
```

This is appropriate for app remapping and shortcut interpretation. It should not replace the general `kiosk-browser` profile for non-Kousen applications unless those applications understand the high function keys.

## Touch and gesture roadmap

Touch traffic is confirmed, but not decoded. The observed stream is:

```text
char003c / handle 0x003d
11-byte rapidly changing payloads
```

Recommended next steps:

- Add `gatt-notify` support for recording named capture sessions to JSONL.
- Capture labeled gestures in isolation: touch start/end, tap without click, swipe up/down/left/right, circular/scroll motion.
- Preserve raw packet timestamps and payloads.
- Decode fields empirically from multiple captures before emitting gestures.
- Start with diagnostics and a visual/test output before using gestures for runtime control.

Likely future normalized events:

```text
TOUCH_START
TOUCH_MOVE
TOUCH_END
SWIPE_UP
SWIPE_DOWN
SWIPE_LEFT
SWIPE_RIGHT
SCROLL
LONG_PRESS
```

Do not synthesize gestures in production until captures demonstrate repeatable rules.

## Command Center integration roadmap

Command Center should be a management/control plane, not the input runtime.

Useful future Command Center features:

- show service status
- show paired remotes
- show connected/disconnected state
- show profile identity vs physical device address
- show battery level
- test button presses
- edit mappings
- restart/reload `kousen-remote`
- pair/forget remotes

The runtime should still work when Command Center is closed.

## KousenTV and browser-app integration

KousenTV and Command Center should handle standard keyboard events consistently:

```text
ArrowUp
ArrowDown
ArrowLeft
ArrowRight
Enter
Escape
Home
Space
AudioVolumeUp
AudioVolumeDown
AudioVolumeMute
F13
```

This keeps physical keyboards, G20S-style remotes, Siri Remotes, and future controllers on the same contract.

## Deployment recommendations

- Public GitHub is acceptable after sanitizing physical device addresses and local paths.
- Keep the install path explicit: `/opt/kousen-remote`.
- Keep `/etc/default/kousen-remote` as the device/mapping configuration point.
- Keep systemd service install separate from pairing. Pairing may require user presence and should not be hidden inside an unattended install.
- For new machines, install the service with the paired remote address:

```bash
sudo packaging/systemd/install-systemd.sh --device XX:XX:XX:XX:XX:XX
```

## Open questions

- Does Remote #2 produce the same raw button map?
- Do firmware revisions change report characteristic ordering or only object suffixes?
- Can BlueZ report-reference descriptor values identify characteristics more robustly than suffixes like `char0038`?
- What is the best non-root permission model for `/dev/uinput` on the kiosk?
- Should `POWER` become a kiosk-owned `DISPLAY_SLEEP` system action?
- Can touch reports provide reliable swipe/scroll semantics without excessive false positives?
