# HID Monitor Packet Protocol

## Goal

Arduino IDE `Pluggable Monitor` and `Pluggable Discovery` can talk to a
low-speed USB HID device without exposing a virtual COM port.

This document defines a simple device protocol for that monitor path.
It does not reuse the existing `rv003usb` bootloader protocol. The goal is a
clean monitor-oriented transport that is easy to implement on both sides.

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
implementation.

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

## First Implementation Scope

The first usable implementation only needs:

- `PING`
- `WRITE`
- `READ`

`STATUS` is helpful for debugging but not required to get an Arduino monitor
working.
