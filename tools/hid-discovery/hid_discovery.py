#!/usr/bin/env python3
"""Minimal Arduino pluggable discovery skeleton for HID-backed boards."""

from __future__ import annotations

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
        close_handle,
        enumerate_hid_devices,
        get_caps,
        make_hid_monitor_address,
        make_hid_monitor_label,
        open_hid_handle,
    )

from hid_monitor_backend import make_backend
from hid_monitor_protocol import CMD_PING, STATUS_OK, HidMonitorFrame


PROTOCOL_VERSION = 1
PROTOCOL_NAME = "hid-monitor"
PROTOCOL_LABEL = "HID Monitor"


def env_vid() -> str:
    return os.environ.get("ARDUINO_HID_VID", "1209").lower()


def env_pid() -> str:
    return os.environ.get("ARDUINO_HID_PID", "c003").lower()


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
    label = os.environ.get("ARDUINO_HID_PORT_LABEL", "RV003 HID Monitor")
    hardware_id = os.environ.get("ARDUINO_HID_HARDWARE_ID", "stub-device")
    product = os.environ.get("ARDUINO_HID_PRODUCT", "RV003 HID Monitor")

    return make_port(address, label, hardware_id, product, env_vid(), env_pid())


def supports_monitor_protocol(address: str) -> bool:
    backend = None
    try:
        backend = make_backend(address)
        response = backend.exchange(HidMonitorFrame(CMD_PING, 0))
        return response.status == STATUS_OK and response.payload == b"PONG"
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
    for device in enumerate_hid_devices():
        instance_id = device.instance_id.strip()
        if not instance_id:
            continue
        folded = instance_id.casefold()
        if f"vid_{vid}" not in folded or f"pid_{pid}" not in folded:
            continue
        try:
            handle = open_hid_handle(device.device_path)
            try:
                caps = get_caps(handle)
            finally:
                close_handle(handle)
        except OSError:
            continue
        if caps.FeatureReportByteLength < 64:
            continue

        address = make_hid_monitor_address(device)
        if not supports_monitor_protocol(address):
            continue

        label = make_hid_monitor_label(device)
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


def main() -> int:
    for raw_line in sys.stdin:
        if not handle_command(raw_line):
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
