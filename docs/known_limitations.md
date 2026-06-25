# Known Limitations

This project is ready for an initial Windows-focused pre-release, but the
following limitations are intentional for now.

## Platform Support

Only Windows HID access is implemented. The packaged release currently ships
Windows executables for Arduino IDE and Arduino CLI users.

## Arduino Integration Scope

The tools target Arduino CLI and Arduino IDE 2.x through Pluggable Discovery
and Pluggable Monitor. Arduino IDE 1.8.x can still compile and upload sketches,
but its legacy serial monitor does not use this monitor integration path.

## Device Protocol Requirement

Matching the configured VID/PID is not enough. Firmware must implement the HID
monitor packet protocol and pass the version `0x01` `PING`/`PONG` compatibility
check before discovery accepts the interface.

## Session Ownership

The protocol expects one active host-side monitor owner per physical HID monitor
interface. The Windows HID handle is opened with shared read/write access, but
concurrent monitor sessions may race feature-report responses or consume each
other's interrupt IN notifications.

## Package Index Integration

The repository provides the Arduino tool archive shape and example
`package_index.json` entries. Final integration into a board package index must
still choose the release URL, checksum, size, and tool version used by that
board package.

## Validation Coverage

The initial release has been smoke-tested with local Windows executables,
Arduino CLI discovery, Arduino CLI monitor open, and one connected HID monitor
firmware. Broader coverage such as multiple simultaneous devices, long-running
monitor sessions, and Arduino IDE GUI-only workflows should be expanded after
the first pre-release.
