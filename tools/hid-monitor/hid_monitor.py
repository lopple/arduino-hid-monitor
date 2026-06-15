#!/usr/bin/env python3
"""Minimal Arduino pluggable monitor skeleton for HID-backed boards."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import shlex
import sys
import threading
import time
import traceback
from urllib.parse import unquote

SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_DIR = SCRIPT_DIR.parent / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from hid_monitor_backend import HidMonitorBackend, make_backend
from hid_monitor_protocol import (
    CMD_PING,
    CMD_READ,
    CMD_WRITE,
    INPUT_NOTIFICATION_FLAG_TX_READY,
    STATUS_EMPTY,
    STATUS_OK,
    HidMonitorFrame,
    chunk_payload,
)


PROTOCOL_VERSION = 1
PROTOCOL_NAME = "hid-monitor"
LOG_PATH = Path(
    os.environ.get(
        "ARDUINO_HID_MONITOR_LOG",
        str(SCRIPT_DIR.parent.parent / "logs" / "hid-monitor.log"),
    )
)


def log_event(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def enable_input_thread() -> bool:
    return os.environ.get("ARDUINO_HID_ENABLE_INPUT", "1").lower() in {"1", "true", "yes"}


def feature_poll_interval_s() -> float:
    text = os.environ.get("ARDUINO_HID_FEATURE_POLL_MS", "10")
    try:
        value = float(text) / 1000.0
    except ValueError:
        value = 0.1
    return max(0.005, value)


def feature_idle_poll_interval_s() -> float:
    text = os.environ.get("ARDUINO_HID_FEATURE_IDLE_POLL_MS", "200")
    try:
        value = float(text) / 1000.0
    except ValueError:
        value = 0.2
    return max(0.02, value)


def feature_idle_after_empty_reads() -> int:
    text = os.environ.get("ARDUINO_HID_FEATURE_IDLE_AFTER_EMPTY", "5")
    try:
        value = int(text)
    except ValueError:
        value = 5
    return max(1, value)


class MonitorSession:
    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.worker: threading.Thread | None = None
        self.input_worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.board_port: str | None = None
        self.backend: HidMonitorBackend | None = None
        self.exchange_lock = threading.Lock()
        self.sequence = 0

    def is_open(self) -> bool:
        return self.sock is not None

    def next_sequence(self) -> int:
        value = self.sequence
        self.sequence = (self.sequence + 1) & 0xFF
        return value

    def close(self) -> None:
        self.stop_event.set()

        sock = self.sock
        self.sock = None
        self.board_port = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

        backend = self.backend
        self.backend = None
        if backend is not None:
            backend.close()

        worker = self.worker
        self.worker = None
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)

        input_worker = self.input_worker
        self.input_worker = None
        if input_worker is not None and input_worker.is_alive():
            input_worker.join(timeout=1.0)


SESSION = MonitorSession()


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def parse_tcp_address(client_addr: str) -> tuple[str, int]:
    host, sep, port_text = client_addr.rpartition(":")
    if not sep or not host or not port_text:
        raise ValueError(f"invalid TCP address: {client_addr}")

    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"invalid TCP port in {client_addr}") from exc

    return host, port


def parse_open_command(line: str) -> tuple[str, str]:
    parts = shlex.split(line)
    if len(parts) != 3:
        raise ValueError("OPEN requires client address and board port")
    _, client_addr, board_port = parts
    return client_addr, board_port


def is_stub_port(board_port: str) -> bool:
    return board_port == "hid://stub"


def is_instance_port(board_port: str) -> bool:
    return board_port.startswith("hid://instance/")


def is_path_port(board_port: str) -> bool:
    return board_port.startswith("hid://path/")


def decode_instance_port(board_port: str) -> str:
    return unquote(board_port.removeprefix("hid://instance/"))


def open_backend_with_ping(board_port: str, attempts: int = 5) -> HidMonitorBackend:
    last_error: Exception | None = None
    last_backend: HidMonitorBackend | None = None
    for attempt in range(1, attempts + 1):
        backend: HidMonitorBackend | None = None
        try:
            backend = make_backend(board_port)
            last_backend = backend
            response = backend.exchange(HidMonitorFrame(CMD_PING, 0))
            if response.status != STATUS_OK or response.payload != b"PONG":
                raise RuntimeError(
                    f"HID monitor ping failed: status={response.status} payload={response.payload!r}"
                )
            if attempt > 1:
                log_event(f"backend open retry succeeded on attempt {attempt}")
            return backend
        except Exception as exc:
            last_error = exc
            log_event(f"backend open attempt {attempt} failed: {exc}")
            if backend is not None and attempt < attempts:
                backend.close()
            time.sleep(0.1)

    if last_backend is not None:
        log_event(f"continuing without successful PING after {attempts} attempts: {last_error}")
        return last_backend
    if last_error is not None:
        raise last_error
    raise RuntimeError("backend open failed")


def exchange_with_retry(backend: HidMonitorBackend, frame: HidMonitorFrame, attempts: int = 3) -> HidMonitorFrame:
    with SESSION.exchange_lock:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return backend.exchange(frame)
            except OSError as exc:
                last_error = exc
                log_event(f"hid exchange attempt {attempt} failed: {exc}")
                backend.reopen()
                time.sleep(0.2)

        if last_error is not None:
            raise last_error
        raise RuntimeError("hid exchange failed")


def drain_feature_reads(sock: socket.socket, backend: HidMonitorBackend, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        response = exchange_with_retry(
            backend,
            HidMonitorFrame(CMD_READ, SESSION.next_sequence()),
        )
        log_event(
            "hid notified read "
            f"status={response.status} payload={response.payload!r}"
        )
        if response.status == STATUS_OK and response.payload:
            sock.sendall(response.payload)
            continue
        if response.status == STATUS_EMPTY:
            return
        stop_event.set()
        return


def input_worker(
    sock: socket.socket,
    backend: HidMonitorBackend,
    stop_event: threading.Event,
) -> None:
    try:
        while not stop_event.is_set():
            notification_flags = backend.read_input_notification()
            if not (notification_flags & INPUT_NOTIFICATION_FLAG_TX_READY):
                continue
            log_event(f"hid notify flags=0x{notification_flags:02x}")
            if stop_event.is_set():
                return
            drain_feature_reads(sock, backend, stop_event)
    except OSError:
        if not stop_event.is_set():
            log_event("input_worker OSError:\n" + traceback.format_exc())
    except Exception:
        if not stop_event.is_set():
            log_event("input_worker unexpected exception:\n" + traceback.format_exc())
    finally:
        stop_event.set()


def backend_worker(
    sock: socket.socket,
    backend: HidMonitorBackend,
    stop_event: threading.Event,
) -> None:
    active_poll_interval = feature_poll_interval_s()
    idle_poll_interval = feature_idle_poll_interval_s()
    idle_after_empty_reads = feature_idle_after_empty_reads()
    poll_interval = active_poll_interval
    empty_read_count = 0
    sock.settimeout(min(0.05, active_poll_interval))
    next_feature_poll = time.monotonic()
    try:
        while not stop_event.is_set():
            timed_out = False
            try:
                data = sock.recv(4096)
            except TimeoutError:
                data = b""
                timed_out = True

            if data:
                empty_read_count = 0
                poll_interval = active_poll_interval
                log_event(f"tcp recv {len(data)} bytes: {data!r}")
                for chunk in chunk_payload(data):
                    frame = HidMonitorFrame(CMD_WRITE, SESSION.next_sequence(), chunk)
                    response = exchange_with_retry(backend, frame)
                    log_event(
                        "hid write "
                        f"len={len(chunk)} status={response.status} payload={response.payload!r}"
                    )
                    if response.status != STATUS_OK:
                        stop_event.set()
                        break
                    if response.payload:
                        sock.sendall(response.payload)
                        continue

                    response = exchange_with_retry(
                        backend,
                        HidMonitorFrame(CMD_READ, SESSION.next_sequence()),
                    )
                    log_event(
                        "hid feature read "
                        f"status={response.status} payload={response.payload!r}"
                    )
                    if response.status == STATUS_OK and response.payload:
                        empty_read_count = 0
                        poll_interval = active_poll_interval
                        sock.sendall(response.payload)
                    elif response.status not in {STATUS_OK, STATUS_EMPTY}:
                        stop_event.set()
                        break
            elif timed_out:
                now = time.monotonic()
                if not backend.has_input_reports() and now >= next_feature_poll:
                    next_feature_poll = now + poll_interval
                    response = exchange_with_retry(
                        backend,
                        HidMonitorFrame(CMD_READ, SESSION.next_sequence()),
                    )
                    if response.status == STATUS_OK and response.payload:
                        empty_read_count = 0
                        poll_interval = active_poll_interval
                        log_event(
                            "hid feature poll "
                            f"status={response.status} payload={response.payload!r}"
                        )
                        sock.sendall(response.payload)
                    elif response.status == STATUS_EMPTY:
                        empty_read_count += 1
                        if empty_read_count >= idle_after_empty_reads:
                            poll_interval = idle_poll_interval
                    elif response.status not in {STATUS_OK, STATUS_EMPTY}:
                        log_event(f"hid feature poll failed status={response.status}")
                        stop_event.set()
                        break
            elif not timed_out:
                break
    except OSError:
        if not stop_event.is_set():
            log_event("backend_worker OSError:\n" + traceback.format_exc())
    except Exception:
        if not stop_event.is_set():
            log_event("backend_worker unexpected exception:\n" + traceback.format_exc())
    finally:
        stop_event.set()
        backend.close()
        try:
            sock.close()
        except OSError:
            pass


def open_session(client_addr: str, board_port: str) -> None:
    log_event(f"open_session client={client_addr!r} board_port={board_port!r}")
    host, port = parse_tcp_address(client_addr)
    sock = socket.create_connection((host, port), timeout=3.0)
    try:
        backend = open_backend_with_ping(board_port)
    except Exception:
        sock.close()
        raise
    SESSION.close()
    SESSION.stop_event.clear()
    SESSION.sock = sock
    SESSION.board_port = board_port
    SESSION.backend = backend
    SESSION.sequence = 0
    if backend.has_input_reports() and enable_input_thread():
        SESSION.input_worker = threading.Thread(
            target=input_worker,
            args=(sock, backend, SESSION.stop_event),
            daemon=True,
            name="hid-monitor-input",
        )
        SESSION.input_worker.start()
    SESSION.worker = threading.Thread(
        target=backend_worker,
        args=(sock, backend, SESSION.stop_event),
        daemon=True,
        name="hid-monitor-session",
    )
    SESSION.worker.start()


def handle_command(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    log_event(f"command {line!r}")

    if line.startswith("HELLO "):
        emit(
            {
                "eventType": "hello",
                "protocolVersion": PROTOCOL_VERSION,
                "message": "OK",
            }
        )
        return True

    if line == "DESCRIBE":
        emit(
            {
                "eventType": "describe",
                "message": "ok",
                "port_description": {
                    "protocol": PROTOCOL_NAME,
                    "configuration_parameters": {},
                },
            }
        )
        return True

    if line.startswith("CONFIGURE "):
        emit({"eventType": "configure", "message": "ok"})
        return True

    if line.startswith("OPEN "):
        try:
            client_addr, board_port = parse_open_command(line)
        except ValueError as exc:
            log_event(f"OPEN parse error: {exc}")
            emit({"eventType": "open", "error": True, "message": str(exc)})
            return True

        if not board_port.startswith("hid://"):
            emit(
                {
                    "eventType": "open",
                    "error": True,
                    "message": f"unsupported board port: {board_port}",
                }
            )
            return True

        if SESSION.is_open():
            emit(
                {
                    "eventType": "open",
                    "error": True,
                    "message": "monitor session is already open",
                }
            )
            return True

        if is_stub_port(board_port) or is_instance_port(board_port) or is_path_port(board_port):
            try:
                open_session(client_addr, board_port)
            except (OSError, ValueError) as exc:
                log_event("OPEN failed:\n" + traceback.format_exc())
                emit({"eventType": "open", "error": True, "message": str(exc)})
                return True
            except Exception as exc:
                log_event("OPEN unexpected failure:\n" + traceback.format_exc())
                emit({"eventType": "open", "error": True, "message": str(exc)})
                return True

            emit({"eventType": "open", "message": "ok"})
            log_event("OPEN ok")
            return True

        emit(
            {
                "eventType": "open",
                "error": True,
                "message": f"unsupported HID address: {board_port}",
            }
        )
        return True

    if line == "CLOSE":
        SESSION.close()
        emit({"eventType": "close", "message": "ok"})
        return True

    if line == "QUIT":
        SESSION.close()
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
