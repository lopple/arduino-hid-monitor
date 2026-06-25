# Arduino HID Monitor Architecture

## Goal

This project exposes a low-speed USB HID transport to Arduino IDE through
Arduino's Pluggable Discovery and Pluggable Monitor APIs.

The goal is not to emulate a kernel serial port. Instead, Arduino IDE opens a
custom `hid-monitor` port, the monitor tool connects to the IDE's TCP monitor
socket, and the tool exchanges HID reports with the device.

## Components

```text
Arduino IDE / Arduino CLI
  |
  +-- Pluggable Discovery
  |      |
  |      +-- enumerate HID devices
  |      +-- return hid-monitor ports as JSON
  |
  +-- Pluggable Monitor
         |
         +-- connect to the IDE monitor TCP socket
         +-- open the selected HID device
         +-- bridge TCP bytes to HID monitor packets
```

## Device Protocol

The device exposes a vendor-defined HID feature report:

- report ID: `0xA0`
- report size: `64 bytes`
- commands: `PING`, `WRITE`, `READ`, `STATUS`, `RESET`

The device may also expose an interrupt IN report:

- report ID: `0xA1`
- report size: `8 bytes`
- role: notify the host that device-to-host monitor bytes are ready

All stream bytes still move through `0xA0` feature reports. The interrupt IN
report is only a wake-up path, so the tool can avoid idle feature-report
polling when firmware supports notifications.

## Session Ownership

The Windows implementation opens HID device handles with shared read/write
access, so the operating system may allow another process to open the same HID
interface at the same time. That does not make concurrent monitor sessions
safe.

The HID monitor protocol is intended to have one active owner per physical
monitor interface. Two tools sending `SetFeature`/`GetFeature` exchanges to the
same interface can race, receive each other's responses, or consume the same
interrupt IN notification.

Future host tools should enforce this at the tool layer, for example with a
per-device lock file or Windows named mutex derived from the resolved
`hid://monitor/...` key or HID device path hash. Diagnostics may still use a
read-only or explicit force mode, but the default user-facing behavior should
avoid opening a device that is already owned by another monitor session.

## Arduino Integration

During local development, a platform can use pattern-based entries:

```text
pluggable_discovery.hid-monitor.pattern="C:\path\to\arduino-hid-monitor\tools\bin\hid-discovery.cmd"
pluggable_monitor.pattern.hid-monitor="C:\path\to\arduino-hid-monitor\tools\bin\hid-monitor.cmd"
```

Released board packages should instead register packaged tools through
`package_index.json` and use:

```text
pluggable_discovery.required=vendor:hid-discovery
pluggable_monitor.required.hid-monitor=vendor:hid-monitor
```

The released package should ship platform-native executables rather than
requiring Arduino IDE users to install Python.

## Future Bootloader Entry

Bootloader entry is intentionally outside the monitor MVP. A future
`hid-reboot` tool can reuse the same HID enumeration and feature-report backend,
but it should stay separate from the monitor stream protocol so upload control
does not depend on the debug monitor being enabled.
