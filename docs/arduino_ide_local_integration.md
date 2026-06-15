# Arduino IDE Local Integration

This note describes the local development setup for using the HID monitor tools
with an installed Arduino platform.

## Requirement

This integration uses Arduino's pluggable discovery and pluggable monitor APIs.
It is intended for Arduino CLI and Arduino IDE 2.x.

Arduino IDE 1.8.x does not route its legacy serial monitor through this
pluggable monitor API, so it cannot use this HID monitor as a drop-in serial
monitor replacement.

## Files

Install these two files next to the target platform's existing `platform.txt` and
`boards.txt`:

- `platform.local.txt`
- `boards.local.txt`

The target directory depends on the Arduino frontend and package vendor:

```text
C:\Users\<user>\AppData\Local\Arduino15\packages\<vendor>\hardware\<arch>\<version>
```

The official standalone `arduino-cli` normally uses `AppData\Local\Arduino15`.
Install the local files into the directory used by the frontend you are testing.

## `platform.local.txt`

This registers the local discovery and monitor tools:

```text
pluggable_discovery.hid-monitor.pattern="C:\path\to\arduino-hid-monitor-tools\tools\bin\hid-discovery.cmd"
pluggable_monitor.pattern.hid-monitor="C:\path\to\arduino-hid-monitor-tools\tools\bin\hid-monitor.cmd"
```

This is the development form documented by Arduino's platform specification.
It avoids package-index tool dependencies while the tools are still local
Python scripts.

## `boards.local.txt`

This lets Arduino identify the selected board from the HID monitor
firmware's VID/PID:

```text
your_board_id.upload_port.vid=1209
your_board_id.upload_port.pid=c003
```

## Expected Flow

1. Flash `hid_monitor_loopback.bin` to the board's user flash area.
2. Restart Arduino IDE.
3. Select the target board.
4. Open the port whose protocol label is `HID Monitor`.
5. Open the monitor.
6. Text sent from the monitor is echoed by the loopback firmware.

The discovery address is intentionally a `hid://path/...` value. This lets the
monitor open the exact Windows HID device path returned by discovery instead of
doing a second lookup by instance ID.

Firmware with an 8-byte `0xA1` input report enables asynchronous
device-to-host output through HID interrupt IN reads. Older feature-only
firmware remains supported, but falls back to reading only after host writes.

## Debug Log

The monitor tool appends debug logs here:

```text
logs\hid-monitor.log
```

This file records commands from Arduino IDE / Arduino CLI and exceptions from
the HID backend. It is intentionally not written to stdout because stdout is
reserved for the pluggable monitor protocol.

## Current Limitations

- The tools currently target Windows.
- The wrappers require `python` to be available on `PATH`.
- The device firmware is a loopback test firmware, not a final Arduino sketch
  runtime.
- This is a development install. A distributable package should ship tool
  binaries and register them via `package_index.json`.
