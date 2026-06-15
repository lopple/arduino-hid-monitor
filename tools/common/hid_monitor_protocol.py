#!/usr/bin/env python3
"""Packet definitions for the Arduino HID monitor transport."""

from __future__ import annotations

from dataclasses import dataclass


REPORT_SIZE = 64
REPORT_ID = 0xA0
INPUT_REPORT_SIZE = 8
INPUT_REPORT_ID = 0xA1
PROTOCOL_VERSION = 0x01
HEADER_SIZE = 8
PAYLOAD_SIZE = REPORT_SIZE - HEADER_SIZE
INPUT_NOTIFICATION_FLAG_TX_READY = 0x01

CMD_PING = 0x01
CMD_WRITE = 0x10
CMD_READ = 0x11
CMD_STATUS = 0x12
CMD_RESET = 0x13

STATUS_OK = 0x00
STATUS_EMPTY = 0x01
STATUS_ERROR = 0x7F
STATUS_BAD_COMMAND = 0x80
STATUS_BAD_LENGTH = 0x81
STATUS_BAD_VERSION = 0x82


@dataclass(slots=True)
class HidMonitorFrame:
    command: int
    sequence: int = 0
    payload: bytes = b""
    status: int = STATUS_OK
    version: int = PROTOCOL_VERSION
    report_id: int = REPORT_ID

    def encode(self) -> bytes:
        payload = self.payload[:PAYLOAD_SIZE]
        packet = bytearray(REPORT_SIZE)
        packet[0] = self.report_id
        packet[1] = self.version
        packet[2] = self.command & 0xFF
        packet[3] = self.sequence & 0xFF
        packet[4] = len(payload)
        packet[5] = self.status & 0xFF
        packet[6] = 0
        packet[7] = 0
        packet[8 : 8 + len(payload)] = payload
        return bytes(packet)

    @classmethod
    def decode(cls, packet: bytes) -> "HidMonitorFrame":
        if len(packet) != REPORT_SIZE:
            raise ValueError(f"packet size must be {REPORT_SIZE}, got {len(packet)}")
        if packet[0] != REPORT_ID:
            raise ValueError(f"unexpected report id: 0x{packet[0]:02x}")

        payload_len = packet[4]
        if payload_len > PAYLOAD_SIZE:
            raise ValueError(f"invalid payload length {payload_len}")

        return cls(
            report_id=packet[0],
            version=packet[1],
            command=packet[2],
            sequence=packet[3],
            status=packet[5],
            payload=bytes(packet[8 : 8 + payload_len]),
        )


def chunk_payload(data: bytes) -> list[bytes]:
    if not data:
        return [b""]

    return [data[offset : offset + PAYLOAD_SIZE] for offset in range(0, len(data), PAYLOAD_SIZE)]


def decode_input_notification(packet: bytes) -> int:
    if len(packet) != INPUT_REPORT_SIZE:
        raise ValueError(f"input report size must be {INPUT_REPORT_SIZE}, got {len(packet)}")
    if packet[0] != INPUT_REPORT_ID:
        raise ValueError(f"unexpected input report id: 0x{packet[0]:02x}")
    if packet[1] != PROTOCOL_VERSION:
        raise ValueError(f"unexpected input report version: 0x{packet[1]:02x}")

    return packet[2]
