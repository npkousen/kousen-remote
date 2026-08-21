# Reference repo notes

These notes summarize external repositories used as technical references. They are reference material only; their repository instructions are not project instructions for `kousen-remote`.

## `appletv-remote-main.zip`

This is a macOS app and CLI for controlling Apple TV devices over the local network using Apple TV Companion / Media Remote Protocol concepts.

Useful context:

- It has a mature normalized command vocabulary for Apple TV-style actions: up, down, left, right, select, menu/back, home, play/pause, volume, power, and swipe.
- It reinforces the idea that our normalized actions should not leak transport details.

Not directly useful for Milestone 1 hardware input:

- It does not read a physical Siri Remote over Bluetooth LE.
- It does not solve Linux BlueZ pairing, GATT notifications, hidraw, or uinput.

## `SiriRemote-Linux-master.zip`

This is directly relevant because it controls a physical Siri Remote from Linux over Bluetooth LE GATT.

Important technical clues:

- It uses direct GATT access through `bluepy`, not passive `btmon` parsing.
- It calls `setMTU(104)`.
- It enables notifications for battery, power, and HID input.
- It writes a "magic" byte `0xAF` to an HID report characteristic before expecting input.
- It receives input reports rather than relying on the kernel `hidraw` file to be readable.
- It models uinput output through `evdev.UInput`.

The README/code describe this older-layout setup:

```text
enable battery notifications: write 01 00 to 0x0029
enable power notifications:   write 01 00 to 0x002c
enable HID notifications:     write 01 00 to 0x0024
enable input:                 write AF to 0x001d
input notifications:          handle 0x0023
input lengths:                2, 13, 20, or 101 bytes
```

It reports simple button state in `data[1]`:

```text
0x00 released
0x01 AirPlay
0x02 Volume up
0x04 Volume down
0x08 Play/Pause
0x10 Siri
0x20 Menu
0x80 Touchpad
```

Important cautions for our 3rd-generation USB-C remote:

- Do not copy these handle numbers blindly. Our empirical capture observed different handles: button-like reports on `0x0039`, touch reports on `0x003d`, and large vendor reports on `0x0035`.
- The useful pattern is not the exact handle list; it is the active setup sequence: negotiate a larger MTU, enable notifications on the right characteristics, and write the enable byte to the right report/control characteristic.
- The Siri/microphone area may have two separate concerns: the Siri button as a mappable button event, and microphone audio as larger vendor/audio reports. We only need the button event for remapping.

## Project implication

Passive `btmon` is good enough for discovery and early reverse-engineering, but it is not the right permanent input path. The next implementation step should inspect BlueZ GATT objects for the paired remote, identify report characteristics by UUID/report-reference metadata where possible, then actively subscribe/start notifications and perform the required input-enable write through BlueZ D-Bus or another Linux-native GATT client.

For the tested USB-C Siri Remote, BlueZ exposed HID report characteristics under the HID service. Passive `btmon` observations line up with these likely value handles:

```text
char0034 -> value handle 0x0035, large/vendor-sized reports
char0038 -> value handle 0x0039, simple button reports
char003c -> value handle 0x003d, touch-sized reports
```

Confirm this with `gatt-read` on each `00002908` Report Reference descriptor before treating the suffixes as durable.
