#!/usr/bin/env python3
"""Backend abstractions for the Arduino HID monitor transport."""

from __future__ import annotations

import os
import platform
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import unquote

from hid_monitor_protocol import (
    CMD_PING,
    CMD_READ,
    CMD_STATUS,
    CMD_WRITE,
    INPUT_REPORT_SIZE,
    PAYLOAD_SIZE,
    STATUS_BAD_COMMAND,
    STATUS_EMPTY,
    STATUS_OK,
    HidMonitorFrame,
    decode_input_notification,
)

if platform.system() == "Windows":
    from windows_hid import (
        close_handle,
        find_hid_device_by_monitor_key,
        find_hid_device_by_instance,
        get_feature,
        get_caps,
        GENERIC_READ,
        open_hid_handle,
        read_file,
        set_feature,
    )

if platform.system() == "Darwin":
    from hid_monitor_config import DEFAULT_PID, DEFAULT_VID
    from macos_hid import MacFeatureReportDevice


def feature_delay_s() -> float:
    text = os.environ.get("ARDUINO_HID_FEATURE_DELAY_MS", "30")
    try:
        return max(0.0, float(text) / 1000.0)
    except ValueError:
        return 0.03


def wait_feature_slot(owner: object) -> None:
    delay = feature_delay_s()
    if delay <= 0:
        return

    now = time.monotonic()
    last_exchange = getattr(owner, "last_feature_exchange", 0.0)
    elapsed = now - last_exchange
    if elapsed < delay:
        time.sleep(delay - elapsed)
    setattr(owner, "last_feature_exchange", time.monotonic())


class HidMonitorBackend:
    def exchange(self, frame: HidMonitorFrame) -> HidMonitorFrame:
        raise NotImplementedError

    def reopen(self) -> None:
        return None

    def has_input_reports(self) -> bool:
        return False

    def read_input_notification(self) -> int:
        return 0

    def close(self) -> None:
        return None


@dataclass
class StubProtocolBackend(HidMonitorBackend):
    """Simple loopback backend that speaks the packet protocol."""

    max_queue: int = 1024

    def __post_init__(self) -> None:
        self._read_queue: deque[int] = deque()

    def exchange(self, frame: HidMonitorFrame) -> HidMonitorFrame:
        if frame.command == CMD_PING:
            return HidMonitorFrame(CMD_PING, frame.sequence, b"PONG", STATUS_OK)

        if frame.command == CMD_WRITE:
            accepted = frame.payload[:PAYLOAD_SIZE]
            space = max(0, self.max_queue - len(self._read_queue))
            accepted = accepted[:space]
            self._read_queue.extend(accepted)
            return HidMonitorFrame(CMD_WRITE, frame.sequence, b"", STATUS_OK)

        if frame.command == CMD_READ:
            count = min(PAYLOAD_SIZE, len(self._read_queue))
            if count == 0:
                return HidMonitorFrame(CMD_READ, frame.sequence, b"", STATUS_EMPTY)

            payload = bytes(self._read_queue.popleft() for _ in range(count))
            return HidMonitorFrame(CMD_READ, frame.sequence, payload, STATUS_OK)

        if frame.command == CMD_STATUS:
            available = min(255, len(self._read_queue))
            free = min(255, max(0, self.max_queue - len(self._read_queue)))
            return HidMonitorFrame(CMD_STATUS, frame.sequence, bytes([available, free]), STATUS_OK)

        return HidMonitorFrame(frame.command, frame.sequence, b"", STATUS_BAD_COMMAND)


class WindowsFeatureReportBackend(HidMonitorBackend):
    def __init__(self, instance_id: str) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("WindowsFeatureReportBackend is only supported on Windows")

        device = find_hid_device_by_instance(instance_id)
        if device is None:
            raise FileNotFoundError(f"HID device not found for instance {instance_id}")

        self.instance_id = instance_id
        self.device_path = device.device_path
        self.handle = open_hid_handle(self.device_path)
        self.input_handle = None
        caps = get_caps(self.handle)
        self.input_report_size = caps.InputReportByteLength
        self.last_feature_exchange = 0.0

    def reopen(self) -> None:
        self.close()
        device = find_hid_device_by_instance(self.instance_id)
        if device is None:
            raise FileNotFoundError(f"HID device not found for instance {self.instance_id}")
        self.device_path = device.device_path
        self.handle = open_hid_handle(self.device_path)
        self.input_handle = None
        caps = get_caps(self.handle)
        self.input_report_size = caps.InputReportByteLength

    def exchange(self, frame: HidMonitorFrame) -> HidMonitorFrame:
        wait_feature_slot(self)
        set_feature(self.handle, frame.encode())
        return HidMonitorFrame.decode(get_feature(self.handle, 64, 0xA0))

    def has_input_reports(self) -> bool:
        return self.input_report_size >= INPUT_REPORT_SIZE

    def read_input_notification(self) -> int:
        if not self.has_input_reports():
            return 0
        if self.input_handle is None:
            self.input_handle = open_hid_handle(self.device_path, GENERIC_READ)
        packet = read_file(self.input_handle, self.input_report_size)
        if not packet:
            return 0
        try:
            return decode_input_notification(packet)
        except ValueError:
            return 0

    def close(self) -> None:
        input_handle = getattr(self, "input_handle", None)
        if input_handle is not None:
            close_handle(input_handle)
            self.input_handle = None

        handle = getattr(self, "handle", None)
        if handle is not None:
            close_handle(handle)
            self.handle = None


class WindowsFeatureReportPathBackend(HidMonitorBackend):
    def __init__(self, device_path: str) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("WindowsFeatureReportPathBackend is only supported on Windows")

        self.device_path = device_path
        self.handle = open_hid_handle(self.device_path)
        self.input_handle = None
        caps = get_caps(self.handle)
        self.input_report_size = caps.InputReportByteLength
        self.last_feature_exchange = 0.0

    def reopen(self) -> None:
        self.close()
        self.handle = open_hid_handle(self.device_path)
        self.input_handle = None
        caps = get_caps(self.handle)
        self.input_report_size = caps.InputReportByteLength

    def exchange(self, frame: HidMonitorFrame) -> HidMonitorFrame:
        wait_feature_slot(self)
        set_feature(self.handle, frame.encode())
        return HidMonitorFrame.decode(get_feature(self.handle, 64, 0xA0))

    def has_input_reports(self) -> bool:
        return self.input_report_size >= INPUT_REPORT_SIZE

    def read_input_notification(self) -> int:
        if not self.has_input_reports():
            return 0
        if self.input_handle is None:
            self.input_handle = open_hid_handle(self.device_path, GENERIC_READ)
        packet = read_file(self.input_handle, self.input_report_size)
        if not packet:
            return 0
        try:
            return decode_input_notification(packet)
        except ValueError:
            return 0

    def close(self) -> None:
        input_handle = getattr(self, "input_handle", None)
        if input_handle is not None:
            close_handle(input_handle)
            self.input_handle = None

        handle = getattr(self, "handle", None)
        if handle is not None:
            close_handle(handle)
            self.handle = None


class WindowsFeatureReportMonitorBackend(WindowsFeatureReportPathBackend):
    def __init__(self, monitor_key: str) -> None:
        device = find_hid_device_by_monitor_key(monitor_key)
        if device is None:
            raise FileNotFoundError(f"HID monitor device not found for key {monitor_key}")

        self.monitor_key = monitor_key
        super().__init__(device.device_path)

    def reopen(self) -> None:
        self.close()
        device = find_hid_device_by_monitor_key(self.monitor_key)
        if device is None:
            raise FileNotFoundError(f"HID monitor device not found for key {self.monitor_key}")
        self.device_path = device.device_path
        self.handle = open_hid_handle(self.device_path)
        self.input_handle = None
        caps = get_caps(self.handle)
        self.input_report_size = caps.InputReportByteLength


class MacFeatureReportBackend(HidMonitorBackend):
    def __init__(self, address_token: str) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError("MacFeatureReportBackend is only supported on macOS")

        token = unquote(address_token)
        parts = token.split(":")
        if len(parts) == 3:
            vid_text, pid_text, registry_text = parts
        elif len(parts) == 1:
            vid_text, pid_text, registry_text = DEFAULT_VID, DEFAULT_PID, parts[0]
        else:
            raise ValueError(f"unsupported macOS HID address token: {token}")

        self.vid = int(vid_text, 16)
        self.pid = int(pid_text, 16)
        self.registry_id = int(registry_text, 16)
        self.device = MacFeatureReportDevice(self.registry_id, self.vid, self.pid)
        self.last_feature_exchange = 0.0

    def reopen(self) -> None:
        self.close()
        self.device = MacFeatureReportDevice(self.registry_id, self.vid, self.pid)

    def exchange(self, frame: HidMonitorFrame) -> HidMonitorFrame:
        wait_feature_slot(self)
        self.device.set_feature(frame.encode())
        return HidMonitorFrame.decode(self.device.get_feature(64, 0xA0))

    def close(self) -> None:
        device = getattr(self, "device", None)
        if device is not None:
            device.close()
            self.device = None


def make_backend(board_port: str) -> HidMonitorBackend:
    if board_port == "hid://stub":
        return StubProtocolBackend()

    if board_port.startswith("hid://macos/"):
        return MacFeatureReportBackend(board_port.removeprefix("hid://macos/"))

    if board_port.startswith("hid://monitor/"):
        monitor_key = unquote(board_port.removeprefix("hid://monitor/"))
        return WindowsFeatureReportMonitorBackend(monitor_key)

    if board_port.startswith("hid://instance/"):
        instance_id = unquote(board_port.removeprefix("hid://instance/"))
        return WindowsFeatureReportBackend(instance_id)

    if board_port.startswith("hid://path/"):
        device_path = unquote(board_port.removeprefix("hid://path/"))
        return WindowsFeatureReportPathBackend(device_path)

    raise ValueError(f"unsupported HID address: {board_port}")
