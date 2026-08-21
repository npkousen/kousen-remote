# kousen-remote

`kousen-remote` is a standalone Linux application/service for making Bluetooth remotes usable as ordinary Linux input devices. The initial target is the Apple Siri Remote 3rd generation USB-C model on Debian through BlueZ.

This project is not part of KousenTV. The intended contract is:

```text
Apple Siri Remote
  -> Bluetooth LE / BlueZ
  -> kousen-remote
  -> normalized remote actions
  -> Linux uinput virtual input device
  -> keyboard/media events
  -> Chromium / KousenTV / VLC / other applications
```

KousenTV should receive normal browser/Linux input and should not contain Apple-specific Bluetooth code.

## Milestone 1 Scope

Implemented in this repository:

- clean Python package and CLI skeleton
- machine-readable device profiles in `profiles/`
- BlueZ D-Bus discovery using LE and HID discovery filters where available
- candidate scoring with explanations
- BlueZ device inspection
- pairing/trust/connect through BlueZ D-Bus
- Linux `hidraw` inspection by vendor/product instead of fixed device number
- diagnostic raw event monitor for comparing paired physical remotes
- normalized action vocabulary and configurable action-to-key mapping model
- tests for profile matching, scoring, event vocabulary, mapping, and raw report classification

Milestone 2 adds:

- active BlueZ GATT button notifications from the Siri Remote report characteristic
- raw report decoding to normalized actions
- default kiosk/browser key mapping in `mappings/kiosk-browser.json`
- Linux uinput output through `python-evdev`
- print-only runtime output for safe SSH testing before injecting real input
- systemd installer templates for kiosk deployment

Still not implemented:

- speculative gesture behavior
- decoded touch gestures
- udev rules or persistent host Bluetooth changes
- web UI
- KousenTV or Command Center integration

## Known Siri Remote Profile

The empirical baseline comes from prior Debian testing of one Apple Siri Remote 3rd generation USB-C unit.

Known model signals:

- Apple manufacturer ID: `0x004c`
- Product: `0315`
- Modalias: `bluetooth:v004Cp0315d0001`
- Bluetooth HID identity: `0005:004C:0315`
- Appearance: `0x03c0`
- HID service: `00001812-0000-1000-8000-00805f9b34fb`
- Vendor service observed: `8341f2b4-c013-4f04-8197-c4cdb42e26dc`

One previously tested physical unit had a stable public Bluetooth address. That address identifies one remote, not the model. Device profiles match hardware family characteristics; physical devices are separate instances.

Known raw report observations:

- button notifications were observed as two-byte values
- `0000` behaved as release/neutral
- active GATT capture labeled navigation, select, back, home, media, volume, power, and Siri/Mic button values
- touch traffic was observed but not decoded

## Architecture

The code keeps these boundaries:

- `discovery/`: BlueZ scanning and candidate scoring
- `pairing/`: pairing-oriented entry points
- `devices/`: Linux device inspection, currently `hidraw`
- `drivers/apple_siri_remote_3/`: Apple-specific raw report knowledge
- `mapping/`: normalized actions and action-to-key mappings
- `outputs/uinput/`: reserved for Milestone 2 output implementation
- `service/`: reserved for daemon runtime
- `cli/`: terminal workflow for development and diagnostics

Hardware-specific drivers should emit normalized actions. Mapping code translates normalized actions to Linux key codes. Applications should never consume raw Apple report bytes directly.

## Development

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Run tests:

```bash
python -m unittest discover -s tests
```

Show CLI help:

```bash
python -m kousen_remote --help
```

## CLI Workflow

Scan for likely compatible remotes:

```bash
kousen-remote scan --seconds 10
```

If BlueZ filtering hides useful advertisement data, scan without the HID UUID filter:

```bash
kousen-remote scan --seconds 10 --no-hid-filter --all
```

List known BlueZ devices and why they match:

```bash
kousen-remote devices --all
```

Inspect one device:

```bash
kousen-remote info XX:XX:XX:XX:XX:XX
```

Inspect paired-device GATT layout:

```bash
kousen-remote gatt XX:XX:XX:XX:XX:XX
```

Read HID report-reference descriptors:

```bash
kousen-remote gatt-read XX:XX:XX:XX:XX:XX desc003b
```

Actively subscribe to a report characteristic:

```bash
kousen-remote gatt-notify XX:XX:XX:XX:XX:XX char0038
```

Run the daemon path in print-only mode:

```bash
kousen-remote run --output print --mapping mappings/kiosk-browser.json XX:XX:XX:XX:XX:XX
```

Run the daemon path with Linux uinput output:

```bash
sudo ~/kousen-remote/.venv/bin/kousen-remote run --mapping mappings/kiosk-browser.json XX:XX:XX:XX:XX:XX
```

The uinput mode creates a virtual keyboard/media device named `kousen-remote`. Applications receive normal Linux key events.

The runtime reconnects by default. If the remote is asleep when the service starts, it will retry connection/GATT subscription until the remote wakes.

Install as a systemd service:

```bash
sudo packaging/systemd/install-systemd.sh --device XX:XX:XX:XX:XX:XX
```

Install with the Kousen app-remapping profile:

```bash
sudo packaging/systemd/install-systemd.sh --device XX:XX:XX:XX:XX:XX --mapping kousen-control
```

See [docs/systemd.md](docs/systemd.md) before running the installer; it lists the system paths and packages touched.

Pair, trust, and connect:

```bash
kousen-remote pair XX:XX:XX:XX:XX:XX
```

Inspect matching `hidraw` devices:

```bash
kousen-remote hidraw
```

Monitor raw reports for Remote #1/#2 comparison:

```bash
kousen-remote test --hidraw /dev/hidrawN
```

Reading `/dev/hidraw*` may require permissions or `sudo` depending on the host. Do not add udev rules until the exact rule is reviewed.

If the Linux `hidraw` device is present but does not produce readable input reports, use the development-only `btmon` parser:

```bash
sudo ~/kousen-remote/.venv/bin/kousen-remote btmon-test
```

For labeled button capture, suppress touch traffic:

```bash
sudo ~/kousen-remote/.venv/bin/kousen-remote btmon-test --buttons-only
```

This is a diagnostic capture path, not the intended permanent runtime dependency.

## Remote #2 Clean-Room Checklist

Use `scan`, `info`, `hidraw`, and `test` to answer:

1. Does it advertise Apple manufacturer data `0x004c`?
2. Does it expose appearance `0x03c0`?
3. Does it resolve to modalias `bluetooth:v004Cp0315d0001`?
4. Does it expose Vendor/Product `004C:0315`?
5. Does it expose the HID service UUID?
6. Does it produce the same raw button values?
7. Does touch activity produce an equivalent raw report stream?
8. Can the same profile support both physical devices?
9. Can both units remain paired independently?

## Reference Repositories

See [docs/reference-repos.md](docs/reference-repos.md) for notes on external Apple TV/Siri Remote projects and which parts are relevant to this Linux hardware-input service.

## Development Notes

See [docs/development-notes.md](docs/development-notes.md) for lessons learned, button mappings, Power-button handling, touch/gesture roadmap, and future Command Center/KousenTV integration notes.

## Public Pages

This repo includes a public installation guide in `index.html` and a privacy policy in `privacy/index.html`. Both pages can be served directly by GitHub Pages from the repository root.

## Relationship To KousenTV And Kiosk Work

`kousen-remote` should eventually run as its own lightweight service on the kiosk. KousenTV, Chromium, VLC, and other applications should see standard input events. Command Center may later manage pairing/testing/configuration, but it must not be required for remote input to function.

Default kiosk/browser mapping:

```text
NAV_UP        -> KEY_UP
NAV_DOWN      -> KEY_DOWN
NAV_LEFT      -> KEY_LEFT
NAV_RIGHT     -> KEY_RIGHT
SELECT        -> KEY_ENTER
BACK          -> KEY_ESC
HOME          -> KEY_HOME
PLAY_PAUSE    -> KEY_SPACE
VOLUME_UP     -> KEY_VOLUMEUP
VOLUME_DOWN   -> KEY_VOLUMEDOWN
MUTE          -> KEY_MUTE
POWER         -> unmapped by default
SIRI          -> KEY_F13
```

`POWER` is intentionally unmapped in the kiosk/browser profile because emitting `KEY_POWER` can trigger the host OS power-button behavior.

Alternative Kousen stack mapping:

`mappings/kousen-control.json` maps the Siri/Mic button to `KEY_HOME` so the kiosk can always return to `kousen.cc`. The remaining twelve buttons use high function keys for app-level remapping:

```text
NAV_UP        -> KEY_F13
NAV_RIGHT     -> KEY_F14
NAV_DOWN      -> KEY_F15
NAV_LEFT      -> KEY_F16
SELECT        -> KEY_F17
BACK          -> KEY_F18
HOME          -> KEY_F19
PLAY_PAUSE    -> KEY_F20
MUTE          -> KEY_F21
VOLUME_UP     -> KEY_F22
VOLUME_DOWN   -> KEY_F23
POWER         -> KEY_F24
SIRI          -> KEY_HOME
```

Linux evdev provides standard function keys through `KEY_F24`; `KEY_F25` is not portable.

## License

This project is open source under the MIT License. See `LICENSE` for details.
