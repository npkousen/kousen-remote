# Milestone 2: raw reports to uinput

The next milestone should turn verified raw reports into normal Linux input.

## Goals

- capture labeled button sessions for Remote #1 and Remote #2
- attach definitive semantic labels to raw two-byte button values
- discover stable GATT characteristic paths instead of relying on ATT handles
- implement active GATT input setup, including notification subscription, MTU considerations, and the Siri Remote input-enable write observed in reference implementations
- implement `AppleSiriRemote3` raw report decoding to normalized actions
- implement a minimal uinput output backend
- add a daemon loop that reconnects to trusted remotes and stays idle when no remote is active
- add systemd unit files without installing them automatically
- document required group/udev permissions for `/dev/uinput` and any diagnostic `hidraw` access

## Current status

Implemented:

- active GATT notification capture for the observed button report characteristic
- labeled Remote #1 button map, including Mic/Siri as `SIRI`
- normalized action dispatch
- print-only output for safe testing
- uinput output through `python-evdev`
- default kiosk/browser mapping file
- systemd unit and default environment-file templates
- reconnect/backoff behavior for sleeping or disconnected remotes

Remaining:

- validate Remote #2 uses the same profile map
- decide reviewed udev/group policy for `/dev/uinput`
- decode touch gestures

## Non-goals

- web management UI
- Command Center integration
- speculative gesture decoding
- host suspend/wake automation

## Validation

Milestone 2 is complete when a paired supported remote can emit a small verified subset of normalized actions through uinput, and a normal application receives Linux key/media events without knowing about Apple Bluetooth reports.
