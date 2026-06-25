#!/usr/bin/env python3
"""Small CLI for probing the HID monitor packet protocol."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import time
from urllib.parse import unquote

SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_DIR = SCRIPT_DIR.parent / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from hid_monitor_backend import make_backend
from hid_monitor_config import add_usb_id_arguments, resolve_usb_ids
from hid_monitor_protocol import (
    CMD_PING,
    CMD_READ,
    CMD_STATUS,
    CMD_WRITE,
    HidMonitorFrame,
    is_supported_ping_response,
)
from windows_hid import (
    enumerate_hid_devices,
    get_caps,
    open_hid_handle,
    close_handle,
    enumerate_hid_monitor_devices,
    find_hid_device_by_instance,
    make_hid_monitor_address,
)


def find_default_board_port(vid: str, pid: str) -> str:
    wanted_vid = f"vid_{vid.casefold()}"
    wanted_pid = f"pid_{pid.casefold()}"

    candidate_devices = [
        device
        for device in enumerate_hid_devices()
        if wanted_vid in device.instance_id.casefold() and wanted_pid in device.instance_id.casefold()
    ]
    monitor_devices = enumerate_hid_monitor_devices(candidate_devices)
    for device in monitor_devices:
        address = make_hid_monitor_address(device, monitor_devices)
        backend = None
        try:
            backend = make_backend(address)
            response = backend.exchange(HidMonitorFrame(CMD_PING, 0))
            if is_supported_ping_response(response, expected_sequence=0):
                return address
        except Exception:
            continue
        finally:
            if backend is not None:
                backend.close()

    raise FileNotFoundError(f"no HID device found for VID={vid} PID={pid}")


def exchange(backend, command: int, sequence: int, payload: bytes = b"") -> HidMonitorFrame:
    return backend.exchange(HidMonitorFrame(command, sequence, payload))


def read_input_until_payload(backend, timeout_s: float = 1.0) -> bytes:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        notification_flags = backend.read_input_notification()
        if notification_flags:
            return bytes([notification_flags])
    return b""


def print_caps_for_port(board_port: str) -> None:
    device_path = None

    if board_port.startswith("hid://instance/"):
        instance_id = unquote(board_port.removeprefix("hid://instance/"))
        device = find_hid_device_by_instance(instance_id)
        if device is not None:
            device_path = device.device_path
    elif board_port.startswith("hid://path/"):
        device_path = unquote(board_port.removeprefix("hid://path/"))

    if device_path is None:
        return

    handle = open_hid_handle(device_path)
    try:
        caps = get_caps(handle)
        print(
            "caps="
            f"input:{caps.InputReportByteLength} "
            f"output:{caps.OutputReportByteLength} "
            f"feature:{caps.FeatureReportByteLength}"
        )
    finally:
        close_handle(handle)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="board port such as hid://instance/...")
    add_usb_id_arguments(parser)
    parser.add_argument("--write", default="hello", help="text to send before READ")
    parser.add_argument("--skip-input", action="store_true", help="do not read interrupt IN input reports")
    args = parser.parse_args()

    vid, pid = resolve_usb_ids(args, parser)
    board_port = args.port or find_default_board_port(vid, pid)
    print(f"board_port={board_port}")
    print_caps_for_port(board_port)

    backend = make_backend(board_port)
    try:
        ping = exchange(backend, CMD_PING, 1)
        print(
            "PING "
            f"version={ping.version} command={ping.command} sequence={ping.sequence} "
            f"status={ping.status} payload={ping.payload!r}"
        )

        write_payload = args.write.encode("utf-8")
        write_resp = exchange(backend, CMD_WRITE, 2, write_payload)
        print(f"WRITE status={write_resp.status}")

        if backend.has_input_reports() and not args.skip_input:
            input_payload = read_input_until_payload(backend)
            print(f"INPUT payload={input_payload!r}")
        else:
            read_resp = exchange(backend, CMD_READ, 3)
            print(f"READ status={read_resp.status} payload={read_resp.payload!r}")

        status_resp = exchange(backend, CMD_STATUS, 4)
        print(f"STATUS status={status_resp.status} payload={list(status_resp.payload)}")
    finally:
        backend.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
