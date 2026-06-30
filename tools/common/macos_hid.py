"""Small macOS HID helpers built on ctypes and IOHIDManager."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

corefoundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")

CFAllocatorRef = ctypes.c_void_p
CFTypeRef = ctypes.c_void_p
CFStringRef = ctypes.c_void_p
CFMutableDictionaryRef = ctypes.c_void_p
CFNumberRef = ctypes.c_void_p
CFSetRef = ctypes.c_void_p
IOHIDManagerRef = ctypes.c_void_p
IOHIDDeviceRef = ctypes.c_void_p
IOOptionBits = ctypes.c_uint32
IOReturn = ctypes.c_int32
IOHIDReportType = ctypes.c_int32
io_service_t = ctypes.c_uint32

kCFAllocatorDefault = CFAllocatorRef.in_dll(corefoundation, "kCFAllocatorDefault")

class CFDictionaryKeyCallBacks(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
        ("hash", ctypes.c_void_p),
    ]


class CFDictionaryValueCallBacks(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_long),
        ("retain", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("copyDescription", ctypes.c_void_p),
        ("equal", ctypes.c_void_p),
    ]


kCFTypeDictionaryKeyCallBacks = CFDictionaryKeyCallBacks.in_dll(corefoundation, "kCFTypeDictionaryKeyCallBacks")
kCFTypeDictionaryValueCallBacks = CFDictionaryValueCallBacks.in_dll(corefoundation, "kCFTypeDictionaryValueCallBacks")

kCFNumberSInt32Type = 3
kCFNumberSInt64Type = 4
kCFStringEncodingUTF8 = 0x08000100
kIOHIDReportTypeFeature = 2
kIOHIDOptionsTypeNone = 0

corefoundation.CFStringCreateWithCString.argtypes = [CFAllocatorRef, ctypes.c_char_p, ctypes.c_uint32]
corefoundation.CFStringCreateWithCString.restype = CFStringRef
corefoundation.CFNumberCreate.argtypes = [CFAllocatorRef, ctypes.c_int, ctypes.c_void_p]
corefoundation.CFNumberCreate.restype = CFNumberRef
corefoundation.CFNumberGetValue.argtypes = [CFNumberRef, ctypes.c_int, ctypes.c_void_p]
corefoundation.CFNumberGetValue.restype = ctypes.c_bool
corefoundation.CFStringGetCString.argtypes = [CFStringRef, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
corefoundation.CFStringGetCString.restype = ctypes.c_bool
corefoundation.CFDictionaryCreateMutable.argtypes = [CFAllocatorRef, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
corefoundation.CFDictionaryCreateMutable.restype = CFMutableDictionaryRef
corefoundation.CFDictionarySetValue.argtypes = [CFMutableDictionaryRef, ctypes.c_void_p, ctypes.c_void_p]
corefoundation.CFRelease.argtypes = [CFTypeRef]
corefoundation.CFSetGetCount.argtypes = [CFSetRef]
corefoundation.CFSetGetCount.restype = ctypes.c_long
corefoundation.CFSetGetValues.argtypes = [CFSetRef, ctypes.POINTER(ctypes.c_void_p)]
corefoundation.CFRetain.argtypes = [CFTypeRef]
corefoundation.CFRetain.restype = CFTypeRef

iokit.IOHIDManagerCreate.argtypes = [CFAllocatorRef, IOOptionBits]
iokit.IOHIDManagerCreate.restype = IOHIDManagerRef
iokit.IOHIDManagerSetDeviceMatching.argtypes = [IOHIDManagerRef, CFMutableDictionaryRef]
iokit.IOHIDManagerOpen.argtypes = [IOHIDManagerRef, IOOptionBits]
iokit.IOHIDManagerOpen.restype = IOReturn
iokit.IOHIDManagerClose.argtypes = [IOHIDManagerRef, IOOptionBits]
iokit.IOHIDManagerClose.restype = IOReturn
iokit.IOHIDManagerCopyDevices.argtypes = [IOHIDManagerRef]
iokit.IOHIDManagerCopyDevices.restype = CFSetRef
iokit.IOHIDDeviceGetProperty.argtypes = [IOHIDDeviceRef, CFStringRef]
iokit.IOHIDDeviceGetProperty.restype = CFTypeRef
iokit.IOHIDDeviceOpen.argtypes = [IOHIDDeviceRef, IOOptionBits]
iokit.IOHIDDeviceOpen.restype = IOReturn
iokit.IOHIDDeviceClose.argtypes = [IOHIDDeviceRef, IOOptionBits]
iokit.IOHIDDeviceClose.restype = IOReturn
iokit.IOHIDDeviceSetReport.argtypes = [IOHIDDeviceRef, IOHIDReportType, ctypes.c_long, ctypes.c_void_p, ctypes.c_long]
iokit.IOHIDDeviceSetReport.restype = IOReturn
iokit.IOHIDDeviceGetReport.argtypes = [IOHIDDeviceRef, IOHIDReportType, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_long)]
iokit.IOHIDDeviceGetReport.restype = IOReturn
iokit.IOHIDDeviceGetService.argtypes = [IOHIDDeviceRef]
iokit.IOHIDDeviceGetService.restype = io_service_t
iokit.IORegistryEntryGetRegistryEntryID.argtypes = [io_service_t, ctypes.POINTER(ctypes.c_uint64)]
iokit.IORegistryEntryGetRegistryEntryID.restype = IOReturn


def _cfstr(text: str) -> CFStringRef:
    return corefoundation.CFStringCreateWithCString(kCFAllocatorDefault, text.encode("utf-8"), kCFStringEncodingUTF8)


KEY_VENDOR_ID = _cfstr("VendorID")
KEY_PRODUCT_ID = _cfstr("ProductID")
KEY_PRODUCT = _cfstr("Product")
KEY_MANUFACTURER = _cfstr("Manufacturer")
KEY_SERIAL = _cfstr("SerialNumber")


@dataclass
class MacHidDevice:
    registry_id: int
    vendor_id: int
    product_id: int
    product: str
    manufacturer: str
    serial_number: str


def _cf_number(value: int) -> CFNumberRef:
    number = ctypes.c_int32(value)
    return corefoundation.CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt32Type, ctypes.byref(number))


def _property_number(device: IOHIDDeviceRef, key: CFStringRef) -> int | None:
    prop = iokit.IOHIDDeviceGetProperty(device, key)
    if not prop:
        return None
    out = ctypes.c_int64()
    if not corefoundation.CFNumberGetValue(prop, kCFNumberSInt64Type, ctypes.byref(out)):
        return None
    return int(out.value)


def _property_string(device: IOHIDDeviceRef, key: CFStringRef) -> str:
    prop = iokit.IOHIDDeviceGetProperty(device, key)
    if not prop:
        return ""
    buffer = ctypes.create_string_buffer(1024)
    if not corefoundation.CFStringGetCString(prop, buffer, len(buffer), kCFStringEncodingUTF8):
        return ""
    return buffer.value.decode("utf-8", errors="replace")


def _registry_id(device: IOHIDDeviceRef) -> int:
    service = iokit.IOHIDDeviceGetService(device)
    out = ctypes.c_uint64()
    if not service or iokit.IORegistryEntryGetRegistryEntryID(service, ctypes.byref(out)) != 0:
        return 0
    return int(out.value)


def _make_matching_dict(vid: int, pid: int) -> CFMutableDictionaryRef:
    matching = corefoundation.CFDictionaryCreateMutable(
        kCFAllocatorDefault,
        0,
        ctypes.byref(kCFTypeDictionaryKeyCallBacks),
        ctypes.byref(kCFTypeDictionaryValueCallBacks),
    )
    if not matching:
        raise OSError("CFDictionaryCreateMutable failed")

    vid_number = _cf_number(vid)
    pid_number = _cf_number(pid)
    corefoundation.CFDictionarySetValue(matching, KEY_VENDOR_ID, vid_number)
    corefoundation.CFDictionarySetValue(matching, KEY_PRODUCT_ID, pid_number)
    corefoundation.CFRelease(vid_number)
    corefoundation.CFRelease(pid_number)
    return matching


class MacHidManager:
    def __init__(self, vid: int, pid: int) -> None:
        self.manager = iokit.IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone)
        if not self.manager:
            raise OSError("IOHIDManagerCreate failed")
        matching = _make_matching_dict(vid, pid)
        try:
            iokit.IOHIDManagerSetDeviceMatching(self.manager, matching)
        finally:
            corefoundation.CFRelease(matching)
        self.opened = False

    def close(self) -> None:
        if self.manager:
            if getattr(self, "opened", False):
                iokit.IOHIDManagerClose(self.manager, kIOHIDOptionsTypeNone)
            corefoundation.CFRelease(self.manager)
            self.manager = None

    def __enter__(self) -> "MacHidManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def devices(self) -> list[IOHIDDeviceRef]:
        device_set = iokit.IOHIDManagerCopyDevices(self.manager)
        if not device_set:
            return []
        try:
            count = corefoundation.CFSetGetCount(device_set)
            values = (ctypes.c_void_p * count)()
            corefoundation.CFSetGetValues(device_set, values)
            return [IOHIDDeviceRef(value) for value in values]
        finally:
            corefoundation.CFRelease(device_set)


def enumerate_macos_hid_devices(vid: int, pid: int) -> list[MacHidDevice]:
    with MacHidManager(vid, pid) as manager:
        devices = []
        for device in manager.devices():
            registry_id = _registry_id(device)
            if not registry_id:
                continue
            devices.append(
                MacHidDevice(
                    registry_id=registry_id,
                    vendor_id=_property_number(device, KEY_VENDOR_ID) or vid,
                    product_id=_property_number(device, KEY_PRODUCT_ID) or pid,
                    product=_property_string(device, KEY_PRODUCT) or "HID Monitor",
                    manufacturer=_property_string(device, KEY_MANUFACTURER),
                    serial_number=_property_string(device, KEY_SERIAL),
                )
            )
        return devices


def make_macos_hid_monitor_address(device: MacHidDevice) -> str:
    return f"hid://macos/{device.vendor_id:04x}:{device.product_id:04x}:{device.registry_id:x}"


def make_macos_hid_monitor_label(device: MacHidDevice) -> str:
    if device.serial_number:
        return f"{device.product} ({device.serial_number})"
    return device.product or "HID Monitor"


class MacFeatureReportDevice:
    def __init__(self, registry_id: int, vid: int, pid: int) -> None:
        self.manager = MacHidManager(vid, pid)
        self.device = None
        for candidate in self.manager.devices():
            if _registry_id(candidate) == registry_id:
                self.device = IOHIDDeviceRef(corefoundation.CFRetain(candidate))
                break
        if not self.device:
            self.manager.close()
            raise FileNotFoundError(f"macOS HID device not found for registry id {registry_id:x}")
        result = iokit.IOHIDDeviceOpen(self.device, kIOHIDOptionsTypeNone)
        if result != 0:
            corefoundation.CFRelease(self.device)
            self.manager.close()
            raise OSError(result, "IOHIDDeviceOpen failed")

    def set_feature(self, payload: bytes) -> int:
        if not payload:
            raise ValueError("feature report payload must include a report id")
        buffer = ctypes.create_string_buffer(payload, len(payload))
        result = iokit.IOHIDDeviceSetReport(
            self.device,
            kIOHIDReportTypeFeature,
            payload[0],
            buffer,
            len(payload),
        )
        if result != 0:
            raise OSError(result, "IOHIDDeviceSetReport failed")
        return len(payload)

    def get_feature(self, report_size: int, report_id: int) -> bytes:
        buffer = ctypes.create_string_buffer(report_size)
        buffer[0] = report_id.to_bytes(1, "little")
        length = ctypes.c_long(report_size)
        result = iokit.IOHIDDeviceGetReport(
            self.device,
            kIOHIDReportTypeFeature,
            report_id,
            buffer,
            ctypes.byref(length),
        )
        if result != 0:
            raise OSError(result, "IOHIDDeviceGetReport failed")
        return bytes(buffer.raw[: length.value])

    def close(self) -> None:
        device = getattr(self, "device", None)
        if device:
            iokit.IOHIDDeviceClose(device, kIOHIDOptionsTypeNone)
            corefoundation.CFRelease(device)
            self.device = None
        manager = getattr(self, "manager", None)
        if manager:
            manager.close()
            self.manager = None