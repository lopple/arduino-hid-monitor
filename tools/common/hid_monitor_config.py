#!/usr/bin/env python3
"""Configuration helpers for HID monitor tools."""

from __future__ import annotations

import argparse
import os
import re
import sys


DEFAULT_VID = "1209"
DEFAULT_PID = "c003"
ENV_VID = "ARDUINO_HID_VID"
ENV_PID = "ARDUINO_HID_PID"


def normalize_usb_id(value: str, name: str) -> str:
    text = value.strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if not re.fullmatch(r"[0-9a-f]{1,4}", text):
        raise ValueError(f"{name} must be 1-4 hexadecimal digits, got {value!r}")
    return text.zfill(4)


def resolve_usb_id(
    *,
    arg_value: str | None,
    env_name: str,
    default_value: str,
    name: str,
) -> str:
    env_value = os.environ.get(env_name)
    selected_value = arg_value if arg_value is not None else env_value or default_value
    selected = normalize_usb_id(selected_value, name)

    if arg_value is not None and env_value:
        env_normalized = normalize_usb_id(env_value, env_name)
        if env_normalized != selected:
            sys.stderr.write(
                f"warning: --{name.lower()}={selected} overrides {env_name}={env_normalized}\n"
            )
            sys.stderr.flush()

    return selected


def add_usb_id_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--vid",
        help=f"USB vendor ID, overriding {ENV_VID}; default {DEFAULT_VID}",
    )
    parser.add_argument(
        "--pid",
        help=f"USB product ID, overriding {ENV_PID}; default {DEFAULT_PID}",
    )


def resolve_usb_ids(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[str, str]:
    try:
        vid = resolve_usb_id(
            arg_value=args.vid,
            env_name=ENV_VID,
            default_value=DEFAULT_VID,
            name="VID",
        )
        pid = resolve_usb_id(
            arg_value=args.pid,
            env_name=ENV_PID,
            default_value=DEFAULT_PID,
            name="PID",
        )
    except ValueError as exc:
        parser.error(str(exc))
    return vid, pid
