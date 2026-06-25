#!/usr/bin/env python3
"""Small Windows HID helpers built on ctypes."""

from __future__ import annotations

import ctypes
import hashlib
import re
from ctypes import wintypes
from dataclasses import dataclass

from hid_monitor_protocol import (
    CMD_PING,
    PAYLOAD_SIZE,
    PROTOCOL_VERSION,
    REPORT_ID,
    REPORT_SIZE,
    STATUS_OK,
)


DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


@dataclass(slots=True)
class HidDeviceInfo:
    instance_id: str
    device_path: str


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _check_bool(ok: int, name: str) -> None:
    if not ok:
        raise OSError(ctypes.get_last_error(), f"{name} failed")


def get_hid_guid() -> GUID:
    guid = GUID()
    hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    return guid


def enumerate_hid_devices() -> list[HidDeviceInfo]:
    hid_guid = get_hid_guid()

    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
    ]
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p

    hdevinfo = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(hid_guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if hdevinfo == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevsW failed")

    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(SP_DEVINFO_DATA),
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

    setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(SP_DEVINFO_DATA),
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    setupapi.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL

    devices: list[HidDeviceInfo] = []
    index = 0
    try:
        while True:
            interface_data = SP_DEVICE_INTERFACE_DATA()
            interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

            ok = setupapi.SetupDiEnumDeviceInterfaces(
                hdevinfo,
                None,
                ctypes.byref(hid_guid),
                index,
                ctypes.byref(interface_data),
            )
            if not ok:
                error = ctypes.get_last_error()
                if error == 259:
                    break
                raise OSError(error, "SetupDiEnumDeviceInterfaces failed")

            required_size = wintypes.DWORD()
            devinfo_data = SP_DEVINFO_DATA()
            devinfo_data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)

            setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdevinfo,
                ctypes.byref(interface_data),
                None,
                0,
                ctypes.byref(required_size),
                ctypes.byref(devinfo_data),
            )

            detail_buffer = ctypes.create_string_buffer(required_size.value)
            cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            ctypes.c_ulong.from_buffer(detail_buffer).value = cb_size

            ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
                hdevinfo,
                ctypes.byref(interface_data),
                detail_buffer,
                required_size.value,
                ctypes.byref(required_size),
                ctypes.byref(devinfo_data),
            )
            _check_bool(ok, "SetupDiGetDeviceInterfaceDetailW")

            # SP_DEVICE_INTERFACE_DETAIL_DATA_W stores cbSize first, then the
            # variable-length UTF-16 device path. cbSize is 8 on 64-bit
            # Windows, but the path field still begins immediately after the
            # DWORD field.
            path_offset = ctypes.sizeof(wintypes.DWORD)
            device_path = ctypes.wstring_at(ctypes.addressof(detail_buffer) + path_offset)

            instance_buffer = ctypes.create_unicode_buffer(512)
            ok = setupapi.SetupDiGetDeviceInstanceIdW(
                hdevinfo,
                ctypes.byref(devinfo_data),
                instance_buffer,
                len(instance_buffer),
                None,
            )
            _check_bool(ok, "SetupDiGetDeviceInstanceIdW")

            devices.append(HidDeviceInfo(instance_buffer.value, device_path))
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(hdevinfo)

    return devices


def find_hid_device_by_instance(instance_id: str) -> HidDeviceInfo | None:
    wanted = instance_id.casefold()
    for device in enumerate_hid_devices():
        if device.instance_id.casefold() == wanted:
            return device
    return None


def make_hid_monitor_key(device: HidDeviceInfo, monitor_devices: list[HidDeviceInfo] | None = None) -> str:
    serial = get_hid_serial_number(device.device_path)
    path_hash = make_hid_monitor_hash(device)
    mi = get_hid_interface_number(device)
    if serial:
        serial_label = make_hid_monitor_serial_label(serial)
        if count_monitor_serial(serial, monitor_devices) <= 1:
            return serial_label
        if mi:
            return f"{serial_label}-mi{mi.lower()}"
        return f"{serial_label}-path-{path_hash}"

    if mi:
        return f"mi{mi.lower()}-path-{path_hash}"
    return f"path-{path_hash}"


def make_hid_monitor_hash(device: HidDeviceInfo) -> str:
    return hashlib.sha1(device.device_path.encode("utf-16le")).hexdigest()[:8]


def make_unique_hid_monitor_key(device: HidDeviceInfo, devices: list[HidDeviceInfo]) -> str:
    return make_hid_monitor_key(device, devices)


def make_hid_monitor_address(device: HidDeviceInfo, monitor_devices: list[HidDeviceInfo] | None = None) -> str:
    if monitor_devices is None:
        monitor_devices = enumerate_hid_monitor_devices()
    return "hid://monitor/" + make_unique_hid_monitor_key(device, monitor_devices)


def make_hid_monitor_label(device: HidDeviceInfo, monitor_devices: list[HidDeviceInfo] | None = None) -> str:
    if monitor_devices is None:
        monitor_devices = enumerate_hid_monitor_devices()

    serial = get_hid_serial_number(device.device_path)
    mi = get_hid_interface_number(device)
    path_hash = make_hid_monitor_hash(device)
    if serial:
        serial_label = make_hid_monitor_serial_label(serial)
        if count_monitor_serial(serial, monitor_devices) <= 1:
            return f"RV003USB HID Monitor ({serial_label})"
        if mi:
            return f"RV003USB HID Monitor ({serial_label}, MI {mi})"
        return f"RV003USB HID Monitor ({serial_label}, path {path_hash})"

    if mi:
        return f"RV003USB HID Monitor (MI {mi}, path {path_hash})"
    return f"RV003USB HID Monitor (path {path_hash})"


def get_hid_interface_number(device: HidDeviceInfo) -> str | None:
    match = re.search(r"&mi_([0-9a-f]{2})", device.instance_id.casefold())
    if not match:
        return None
    return match.group(1).upper()


def count_monitor_serial(serial: str, monitor_devices: list[HidDeviceInfo] | None) -> int:
    if monitor_devices is None:
        return 1
    wanted = serial.casefold()
    count = 0
    for device in monitor_devices:
        candidate_serial = get_hid_serial_number(device.device_path)
        if candidate_serial and candidate_serial.casefold() == wanted:
            count += 1
    return count


def make_hid_monitor_serial_label(serial: str) -> str:
    text = serial.strip()
    return re.sub(r"[^0-9a-zA-Z]+", "-", text).strip("-") or "device"


def get_hid_serial_number(device_path: str) -> str | None:
    handle = None
    try:
        handle = open_hid_handle(device_path)
        buffer = ctypes.create_unicode_buffer(126)
        hid.HidD_GetSerialNumberString.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        hid.HidD_GetSerialNumberString.restype = wintypes.BOOLEAN
        ok = hid.HidD_GetSerialNumberString(handle, buffer, ctypes.sizeof(buffer))
        if not ok:
            return None
        return buffer.value.strip() or None
    except OSError:
        return None
    finally:
        if handle is not None:
            close_handle(handle)


def supports_hid_monitor_protocol(device: HidDeviceInfo) -> bool:
    handle = None
    try:
        handle = open_hid_handle(device.device_path)
        caps = get_caps(handle)
        if caps.FeatureReportByteLength < REPORT_SIZE:
            return False

        packet = bytearray(REPORT_SIZE)
        packet[0] = REPORT_ID
        packet[1] = PROTOCOL_VERSION
        packet[2] = CMD_PING
        set_feature(handle, bytes(packet))
        response = get_feature(handle, REPORT_SIZE, REPORT_ID)
        payload_len = response[4]
        if payload_len > PAYLOAD_SIZE:
            return False
        payload = response[8 : 8 + payload_len]
        return (
            response[0] == REPORT_ID
            and response[1] == PROTOCOL_VERSION
            and response[2] == CMD_PING
            and response[3] == 0
            and response[5] == STATUS_OK
            and payload == b"PONG"
        )
    except (OSError, ValueError):
        return False
    finally:
        if handle is not None:
            close_handle(handle)


def enumerate_hid_monitor_devices(devices: list[HidDeviceInfo] | None = None) -> list[HidDeviceInfo]:
    if devices is None:
        devices = enumerate_hid_devices()
    return [device for device in devices if supports_hid_monitor_protocol(device)]


def find_hid_device_by_monitor_key(key: str) -> HidDeviceInfo | None:
    wanted = key.casefold()
    devices = enumerate_hid_monitor_devices()
    for device in devices:
        if make_unique_hid_monitor_key(device, devices).casefold() == wanted:
            return device
    return None


def open_hid_handle(device_path: str, desired_access: int = 0) -> int:
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE

    handle = kernel32.CreateFileW(
        device_path,
        desired_access,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), f"CreateFileW failed for {device_path}")
    return handle


def close_handle(handle: int) -> None:
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def get_caps(handle: int) -> HIDP_CAPS:
    preparsed = ctypes.c_void_p()
    hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN

    ok = hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed))
    _check_bool(ok, "HidD_GetPreparsedData")

    try:
        hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
        hid.HidP_GetCaps.restype = wintypes.LONG
        caps = HIDP_CAPS()
        status = hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
        if status != 0x110000:
            raise OSError(status, "HidP_GetCaps failed")
        return caps
    finally:
        hid.HidD_FreePreparsedData(preparsed)


def set_feature(handle: int, payload: bytes) -> None:
    hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_SetFeature.restype = wintypes.BOOLEAN

    buffer = ctypes.create_string_buffer(payload, len(payload))
    ok = hid.HidD_SetFeature(handle, buffer, len(payload))
    _check_bool(ok, "HidD_SetFeature")


def get_feature(handle: int, report_size: int, report_id: int) -> bytes:
    hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_GetFeature.restype = wintypes.BOOLEAN

    buffer = ctypes.create_string_buffer(report_size)
    buffer[0:1] = bytes([report_id & 0xFF])
    ok = hid.HidD_GetFeature(handle, buffer, report_size)
    _check_bool(ok, "HidD_GetFeature")
    return bytes(buffer.raw[:report_size])


def read_file(handle: int, report_size: int) -> bytes:
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL

    buffer = ctypes.create_string_buffer(report_size)
    bytes_read = wintypes.DWORD()
    ok = kernel32.ReadFile(
        handle,
        buffer,
        report_size,
        ctypes.byref(bytes_read),
        None,
    )
    _check_bool(ok, "ReadFile")
    return bytes(buffer.raw[: bytes_read.value])
