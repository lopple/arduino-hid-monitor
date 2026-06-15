# Arduino package index integration

The release archive is intended to be installed as one Arduino tool named
`arduino-hid-monitor`. It contains:

```text
bin/hid-discovery.exe
bin/hid-monitor.exe
docs/
LICENSE
README.md
metadata.json
```

Board packages can reference the executables from `platform.txt`:

```text
pluggable_discovery.hid-monitor.pattern="{runtime.tools.arduino-hid-monitor.path}/bin/hid-discovery.exe"
pluggable_monitor.pattern.hid-monitor="{runtime.tools.arduino-hid-monitor.path}/bin/hid-monitor.exe"
```

The matching `package_index.json` entries should use the release zip as an
Arduino tool archive. Replace the version, URL, checksum, and size with the
release values:

```json
{
  "tools": [
    {
      "name": "arduino-hid-monitor",
      "version": "0.1.0",
      "systems": [
        {
          "host": "i686-mingw32",
          "archiveFileName": "arduino-hid-monitor-0.1.0-windows-amd64.zip",
          "url": "https://github.com/lopple/arduino-hid-monitor/releases/download/v0.1.0/arduino-hid-monitor-0.1.0-windows-amd64.zip",
          "checksum": "SHA-256:<sha256>",
          "size": "<bytes>"
        }
      ]
    }
  ],
  "platforms": [
    {
      "toolsDependencies": [
        {
          "packager": "lopple",
          "name": "arduino-hid-monitor",
          "version": "0.1.0"
        }
      ]
    }
  ]
}
```

Boards that should appear as HID monitor ports should declare the default
USB VID/PID in `boards.txt`:

```text
your_board_id.upload_port.vid=1209
your_board_id.upload_port.pid=c003
```

The tool defaults are:

- VID: `1209`
- PID: `C003`
- protocol: `hid-monitor`

The VID/PID can be overridden for development or derived board packages with
environment variables:

```text
ARDUINO_HID_VID
ARDUINO_HID_PID
```

The generated `.zip` and `.zip.sha256` files are build outputs. They should be
attached to GitHub Actions artifacts or GitHub Releases, not committed.
