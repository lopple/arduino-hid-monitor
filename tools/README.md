# tools

This directory contains tools for Arduino IDE / Arduino CLI `Pluggable
Discovery` and `Pluggable Monitor` integration.

- `hid-discovery/hid_discovery.py`
  - Enumerates HID devices and exposes matching monitor ports to Arduino.
- `hid-monitor/hid_monitor.py`
  - Bridges Arduino's monitor TCP stream to HID feature reports.
- `hid-probe/hid_monitor_probe.py`
  - Probes the HID monitor packet protocol without Arduino IDE.

The `.cmd` wrappers are for local Windows development. A released board package
should ship platform-specific binaries and register them through
`package_index.json` tool dependencies.
