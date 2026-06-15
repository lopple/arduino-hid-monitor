# arduino-hid-monitor-tools

Arduino IDE / Arduino CLI integration tools for HID-backed monitor ports.

The target device is a low-speed USB HID device, such as `CH32V003 + rv003usb`.
The goal is to use Arduino's pluggable discovery and pluggable monitor APIs
instead of exposing a virtual COM port.

Current status:

- Windows HID discovery works via SetupAPI.
- Windows HID feature-report backend works with the `hid_monitor_loopback`
  firmware.
- `hid_monitor.py` bridges Arduino's monitor TCP stream to HID packets.
- `hid_monitor_probe.py` can directly verify `PING`, `WRITE`, `READ`, and
  `STATUS`.

Default target:

- VID: `0x1209`
- PID: `0xC003`
- protocol: `hid-monitor`

## Quick probe

Flash firmware that implements the HID monitor packet protocol, then run:

```powershell
python .\tools\hid-probe\hid_monitor_probe.py
```

Expected output includes:

```text
PING status=0 payload=b'PONG'
WRITE status=0
READ status=0 payload=b'hello'
STATUS status=0 payload=[0, 255]
```

## Arduino IDE development install

This path targets Arduino CLI / Arduino IDE 2.x pluggable discovery and
pluggable monitor support. Arduino IDE 1.8.x can still compile and upload
sketches, but its legacy serial monitor does not use this pluggable monitor
API.

For local development, add `platform.local.txt` and `boards.local.txt` next to
the target Arduino platform's `platform.txt` and `boards.txt`.

See:

- `examples/local-dev/platform.local.txt`
- `examples/local-dev/boards.local.txt`

These files use this working tree directly and are intended for local testing.
A packaged release should provide compiled tools through `package_index.json`
tool dependencies instead.
