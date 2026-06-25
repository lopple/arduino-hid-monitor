# HID Monitor Packet Protocol

## Goal

Arduino IDE `Pluggable Monitor` and `Pluggable Discovery` can talk to a
low-speed USB HID device without exposing a virtual COM port.

This document defines a simple device protocol for that monitor path.
It does not reuse the existing `rv003usb` bootloader protocol. The goal is a
clean monitor-oriented transport that is easy to implement on both sides.

## Firmware Requirements

A board must ship firmware that implements this HID monitor protocol. Providing
only a generic HID interface with the right VID/PID is not enough; discovery
accepts a port only after it can send a version `0x01` `PING` over the HID
feature report and receive a version `0x01` `PONG`.

The minimum firmware-side requirements are:

- expose a USB HID interface under the board VID/PID
- expose a 64-byte feature report with report ID `0xA0`
- accept host `SetFeature` packets that use the frame format below
- return response frames through `GetFeature` for report ID `0xA0`
- implement `PING`, `WRITE`, and `READ`
- return `BAD_COMMAND`, `BAD_LENGTH`, or `BAD_VERSION` for malformed requests
  when possible

For a usable monitor session, the firmware needs two byte streams:

- host-to-device bytes accepted by `WRITE`
- device-to-host bytes returned by `READ`

The optional interrupt IN report `0xA1` is recommended when the device can spare
an endpoint. It lets firmware notify the tool that device-to-host bytes are
ready. Without it, the monitor still works, but the PC tool falls back to
feature-report polling.

A USB serial string descriptor is recommended for multi-device setups. When it
is present, discovery uses it for the visible monitor label and compact
`hid://monitor/...` address. For example, firmware serial
`RV003-CF33B130D936` is shown as `RV003-CF33B130D936`.

If a monitor-capable HID interface has no readable serial string, discovery
falls back to an explicit path-derived key such as
`hid://monitor/mi02-path-90d86a1a` or `hid://monitor/path-90d86a1a`. The
`path-` marker is intentional so users can tell that the suffix is not a device
serial number. If multiple monitor-capable interfaces report the same serial
string, the interface number is added to keep the address unique.

Discovery filters candidate HID interfaces in this order:

1. instance ID contains the configured VID/PID, default `1209:C003`
2. `FeatureReportByteLength` is at least 64 bytes
3. `PING` returns version `0x01`, the same sequence, status `OK`, and payload
   `PONG`

## Transport Choice

- USB class: `HID`
- control transfer style: `feature report`
- feature report size: `64 bytes`
- feature report ID: `0xA0`
- optional interrupt IN report size: `8 bytes`
- optional interrupt IN report ID: `0xA1`

Using feature reports keeps the transport message-based and avoids relying on
CDC-ACM or a kernel serial driver.

Firmware may also expose an interrupt IN input report as an asynchronous
notification path. The monitor detects this through `InputReportByteLength` and
uses HID reads when available.

## Frame Format

Each logical packet is exactly 64 bytes.

| Offset | Size | Meaning |
| --- | ---: | --- |
| 0 | 1 | report ID (`0xA0`) |
| 1 | 1 | protocol version (`0x01`) |
| 2 | 1 | command |
| 3 | 1 | sequence number |
| 4 | 1 | payload length (`0..56`) |
| 5 | 1 | status |
| 6 | 1 | reserved |
| 7 | 1 | reserved |
| 8 | 56 | payload bytes |

The payload region is always present. Unused bytes are zero-filled.

## Input Report Notification

The optional interrupt IN packet is exactly 8 bytes.

| Offset | Size | Meaning |
| --- | ---: | --- |
| 0 | 1 | report ID (`0xA1`) |
| 1 | 1 | protocol version (`0x01`) |
| 2 | 1 | notification flags |
| 3 | 5 | reserved |

The input report is only a notification path. It tells the PC tool that the
device has monitor bytes ready. The PC tool then drains those bytes with
`CMD_READ` feature reports. This keeps all stream data on one framing path while
avoiding idle feature-report polling.

## Commands

### `0x01` `PING`

Sanity check. Host sends an empty payload. Device replies with:

- protocol version `0x01`
- command `PING`
- same sequence
- status `OK`
- payload `PONG`

### `0x10` `WRITE`

Host pushes bytes toward the device-side monitor stream.

- request payload: monitor bytes
- response payload: empty
- response status: `OK`

The device is free to enqueue those bytes into a TX FIFO, line buffer, or
immediate application callback.

### `0x11` `READ`

Host polls for bytes coming from the device-side monitor stream.

- request payload: empty
- response payload: up to 56 bytes
- response status:
  - `OK` if bytes are returned
  - `EMPTY` if no bytes are available

The host is expected to poll repeatedly while the monitor is open.

### `0x12` `STATUS`

Optional queue telemetry.

Request payload is empty. Response payload is:

| Byte | Meaning |
| ---: | --- |
| 0 | available-to-read bytes, truncated to 255 |
| 1 | free-to-write bytes, truncated to 255 |

### `0x13` `RESET`

Optional control command for future use. Not required for the first monitor
implementation. This is reserved for monitor-session control and does not
define bootloader entry behavior.

## Status Codes

| Value | Name | Meaning |
| ---: | --- | --- |
| `0x00` | `OK` | command succeeded |
| `0x01` | `EMPTY` | no read data available |
| `0x7F` | `ERROR` | generic command failure |
| `0x80` | `BAD_COMMAND` | unknown command |
| `0x81` | `BAD_LENGTH` | malformed payload length |
| `0x82` | `BAD_VERSION` | unsupported protocol version |

## Monitor Mapping

The Arduino monitor process bridges between:

- IDE TCP stream
- HID feature-report request/response packets
- optional HID interrupt IN input reports

The mapping is intentionally simple:

- TCP bytes from IDE -> one or more `WRITE` packets
- interrupt IN input reports -> `READ` wake-up notifications, when available
- `READ` packets -> TCP bytes back to IDE

This keeps the device protocol stream-like while staying packet-oriented on
USB.

Only one host-side monitor session should own a physical HID monitor interface
at a time. The protocol does not define multiplexing or per-client response
routing. If multiple host processes exchange feature reports concurrently,
responses and interrupt IN notifications may be consumed by the wrong process.

## First Implementation Scope

The first usable implementation only needs:

- `PING`
- `WRITE`
- `READ`

`STATUS` is helpful for debugging but not required to get an Arduino monitor
working.

## Out Of Scope: Bootloader Entry

Bootloader entry is intentionally out of scope for the monitor MVP. A future
`hid-reboot` tool may reuse the same HID enumeration and feature-report backend,
but it should use a separate command path so monitor stream I/O and firmware
update control remain clearly separated.
