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
