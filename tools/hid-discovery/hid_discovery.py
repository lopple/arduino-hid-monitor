#!/usr/bin/env python3
"""Minimal Arduino pluggable discovery skeleton for HID-backed boards."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_DIR = SCRIPT_DIR.parent / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

if platform.system() == "Windows":
    from windows_hid import (
        enumerate_hid_devices,
        enumerate_hid_monitor_devices,
        make_hid_monitor_address,
        make_hid_monitor_label,
    )

from hid_monitor_backend import make_backend
from hid_monitor_config import add_usb_id_arguments, resolve_usb_ids
from hid_monitor_protocol import CMD_PING, HidMonitorFrame, is_supported_ping_response


PROTOCOL_VERSION = 1
PROTOCOL_NAME = "hid-monitor"
PROTOCOL_LABEL = "HID Monitor"
CONFIG_VID = "1209"
CONFIG_PID = "c003"


def env_vid() -> str:
    return CONFIG_VID


def env_pid() -> str:
    return CONFIG_PID


def configure(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    add_usb_id_arguments(parser)
    args = parser.parse_args(argv)

    global CONFIG_VID, CONFIG_PID
    CONFIG_VID, CONFIG_PID = resolve_usb_ids(args, parser)


def make_port(
    address: str,
    label: str,
    hardware_id: str,
    product: str,
    vid: str,
    pid: str,
) -> dict:
    return {
        "address": address,
        "label": label,
        "protocol": PROTOCOL_NAME,
        "protocolLabel": PROTOCOL_LABEL,
        "hardwareId": hardware_id,
        "properties": {
            "vid": vid,
            "pid": pid,
            "product": product,
        },
    }


def make_stub_port() -> dict:
    address = os.environ.get("ARDUINO_HID_PORT_ADDRESS", "hid://stub")
    label = os.environ.get("ARDUINO_HID_PORT_LABEL", "HID Monitor")
    hardware_id = os.environ.get("ARDUINO_HID_HARDWARE_ID", "stub-device")
    product = os.environ.get("ARDUINO_HID_PRODUCT", "HID Monitor")

    return make_port(address, label, hardware_id, product, env_vid(), env_pid())


def supports_monitor_protocol(address: str) -> bool:
    backend = None
    try:
        backend = make_backend(address)
        response = backend.exchange(HidMonitorFrame(CMD_PING, 0))
        return is_supported_ping_response(response, expected_sequence=0)
    except Exception:
        return False
    finally:
        if backend is not None:
            backend.close()


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def enumerate_windows_hid_ports() -> list[dict]:
    vid = env_vid()
    pid = env_pid()
    ports = []
    candidate_devices = [
        device
        for device in enumerate_hid_devices()
        if f"vid_{vid}" in device.instance_id.casefold() and f"pid_{pid}" in device.instance_id.casefold()
    ]
    monitor_devices = enumerate_hid_monitor_devices(candidate_devices)
    for device in monitor_devices:
        instance_id = device.instance_id.strip()
        if not instance_id:
            continue

        address = make_hid_monitor_address(device, monitor_devices)
        if not supports_monitor_protocol(address):
            continue

        label = make_hid_monitor_label(device, monitor_devices)
        ports.append(make_port(address, label, instance_id, label, vid, pid))

    return ports


def enumerate_ports() -> list[dict]:
    if os.environ.get("ARDUINO_HID_FORCE_STUB", "").lower() in {"1", "true", "yes"}:
        return [make_stub_port()]

    if platform.system() == "Windows":
        return enumerate_windows_hid_ports()

    return []


def emit_ports(event_type: str) -> None:
    emit(
        {
            "eventType": event_type,
            "ports": enumerate_ports(),
        }
    )


def handle_command(line: str) -> bool:
    line = line.strip()
    if not line:
        return True

    if line.startswith("HELLO "):
        emit(
            {
                "eventType": "hello",
                "protocolVersion": PROTOCOL_VERSION,
                "message": "OK",
            }
        )
        return True

    if line == "START":
        emit({"eventType": "start", "message": "ok"})
        return True

    if line == "START_SYNC":
        emit({"eventType": "start_sync", "message": "OK"})
        for port in enumerate_ports():
            emit({"eventType": "add", "port": port})
        return True

    if line == "LIST":
        emit_ports("list")
        return True

    if line == "STOP":
        emit({"eventType": "stop", "message": "ok"})
        return True

    if line == "QUIT":
        emit({"eventType": "quit", "message": "OK"})
        return False

    emit(
        {
            "eventType": "command_error",
            "error": True,
            "message": f"Unknown command {line}",
        }
    )
    return True


def main(argv: list[str] | None = None) -> int:
    configure(argv)
    for raw_line in sys.stdin:
        if not handle_command(raw_line):
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
