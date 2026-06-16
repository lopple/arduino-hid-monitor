# arduino-hid-monitor

Reference tools for exposing a USB HID device as an Arduino IDE / Arduino CLI
monitor port.

The target device is a low-speed USB HID device, such as `CH32V003 + rv003usb`.
The goal is to use Arduino's Pluggable Discovery and Pluggable Monitor APIs
instead of exposing a virtual COM port.

## Status

This is an experimental MVP.

- Windows HID discovery works via SetupAPI.
- Windows HID feature-report transport works with firmware that implements the
  HID monitor packet protocol.
- `hid_monitor.py` bridges Arduino's monitor TCP stream to HID packets.
- `hid_monitor_probe.py` can directly verify `PING`, `WRITE`, `READ`, and
  `STATUS`.
- Arduino IDE users should eventually receive packaged executables. The Python
  scripts and `.cmd` wrappers are development tools.

## Default Target

- VID: `0x1209`
- PID: `0xC003`
- protocol: `hid-monitor`

The VID/PID can be overridden with environment variables:

```text
ARDUINO_HID_VID
ARDUINO_HID_PID
```

## Protocol

The device protocol is documented in
[`docs/hid_monitor_packet_protocol.md`](docs/hid_monitor_packet_protocol.md).
Board firmware must implement that protocol; matching VID/PID alone is not
enough for discovery.

In short:

- feature report `0xA0`, `64 bytes`, carries monitor commands and stream data
- `PING` must return `PONG` for discovery to accept the HID interface
- optional interrupt IN report `0xA1`, `8 bytes`, notifies the host that
  device-to-host bytes are ready
- stream bytes are drained with `CMD_READ` feature reports

## Quick Probe

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

## Arduino IDE Development Install

This path targets Arduino CLI and Arduino IDE 2.x. Arduino IDE 1.8.x can still
compile and upload sketches, but its legacy serial monitor does not use the
Pluggable Monitor API.

For local development, add `platform.local.txt` and `boards.local.txt` next to
the target Arduino platform's `platform.txt` and `boards.txt`.

See:

- [`examples/local-dev/platform.local.txt`](examples/local-dev/platform.local.txt)
- [`examples/local-dev/boards.local.txt`](examples/local-dev/boards.local.txt)
- [`docs/arduino_ide_local_integration.md`](docs/arduino_ide_local_integration.md)

A released board package should provide compiled tools through
`package_index.json` tool dependencies instead of requiring Python on the user's
machine.

## Windows Release Build

Install build dependencies, then build the Arduino tool archive:

```powershell
python -m pip install -r requirements-build.txt
.\scripts\build-windows-tools.ps1 -PackageVersion 0.1.0
```

The build creates:

```text
release/arduino-hid-monitor-0.1.0-windows-amd64.zip
release/arduino-hid-monitor-0.1.0-windows-amd64.zip.sha256
```

The archive contains standalone Windows executables for Python-free Arduino IDE
installations:

```text
bin/hid-discovery.exe
bin/hid-monitor.exe
```

See
[`docs/package_index_integration.md`](docs/package_index_integration.md)
for the expected Arduino `package_index.json` integration shape.

## Development Checks

Run a syntax check without writing `.pyc` files:

```powershell
python -c "from pathlib import Path; [compile(p.read_text(encoding='utf-8'), str(p), 'exec') for p in Path('tools').rglob('*.py')]; print('syntax ok')"
```

Stub discovery can be tested without hardware:

```powershell
$env:ARDUINO_HID_FORCE_STUB = "1"
"HELLO 1", "START_SYNC", "QUIT" | python .\tools\hid-discovery\hid_discovery.py
```

## License

MIT. See [`LICENSE`](LICENSE).
