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

Explicitly not implemented in Milestone 1:

- speculative raw button label mappings
- decoded touch gestures
- uinput event emission
- systemd installation
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

The previously tested physical unit used address `E0:C3:EA:A1:88:77`. That address identifies one remote, not the model. Device profiles match hardware family characteristics; physical devices are separate instances.

Known raw report observations:

- button notifications were observed as two-byte values
- `0000` behaved as release/neutral
- observed nonzero button values were `0100`, `0200`, `0400`, `1000`, `2000`, `4000`, `8000`, and `0001`
- the surviving transcript does not establish trustworthy physical button labels for those values
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
kousen-remote info E0:C3:EA:A1:88:77
```

Inspect paired-device GATT layout:

```bash
kousen-remote gatt E0:C3:EA:A1:88:77
```

Read HID report-reference descriptors:

```bash
kousen-remote gatt-read E0:C3:EA:A1:88:77 desc003b
```

Actively subscribe to a report characteristic:

```bash
kousen-remote gatt-notify E0:C3:EA:A1:88:77 char0038
```

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

## Relationship To KousenTV And Kiosk Work

`kousen-remote` should eventually run as its own lightweight service on the kiosk. KousenTV, Chromium, VLC, and other applications should see standard input events. Command Center may later manage pairing/testing/configuration, but it must not be required for remote input to function.
