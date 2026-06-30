#!/bin/sh
set -eu

package_version="${1:-0.0.0-dev}"
repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
build_root="$repo_root/build"
release_root="$repo_root/release"
package_root="$build_root/package/arduino-hid-monitor"
archive_name="arduino-hid-monitor-$package_version-macos-universal.zip"
archive_path="$release_root/$archive_name"

rm -rf "$build_root/package" "$release_root"
mkdir -p "$package_root/bin" "$package_root/lib" "$package_root/docs" "$release_root"

cp -R "$repo_root/tools/common" "$package_root/lib/common"
cp -R "$repo_root/tools/hid-discovery" "$package_root/lib/hid-discovery"
cp -R "$repo_root/tools/hid-monitor" "$package_root/lib/hid-monitor"
cp "$repo_root/LICENSE" "$package_root/LICENSE"
cp "$repo_root/README.md" "$package_root/README.md"
cp "$repo_root/docs/package_index_integration.md" "$package_root/docs/package_index_integration.md"
cp "$repo_root/docs/hid_monitor_packet_protocol.md" "$package_root/docs/hid_monitor_packet_protocol.md"

cat > "$package_root/bin/hid-discovery" <<'EOF'
#!/bin/sh
set -eu
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec /usr/bin/env python3 "$script_dir/../lib/hid-discovery/hid_discovery.py" "$@"
EOF

cat > "$package_root/bin/hid-monitor" <<'EOF'
#!/bin/sh
set -eu
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec /usr/bin/env python3 "$script_dir/../lib/hid-monitor/hid_monitor.py" "$@"
EOF
chmod +x "$package_root/bin/hid-discovery" "$package_root/bin/hid-monitor"
find "$package_root/lib" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$package_root/metadata.json" <<EOF
{
  "name": "arduino-hid-monitor",
  "version": "$package_version",
  "protocol": "hid-monitor",
  "defaultVid": "1209",
  "defaultPid": "C003",
  "platform": "macos-universal"
}
EOF

(
  cd "$build_root/package"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "arduino-hid-monitor" "$archive_path"
)

(
  cd "$release_root"
  shasum -a 256 "$archive_name" | sed "s/  / */" > "$archive_name.sha256"
)

printf 'Archive: %s\n' "$archive_path"
printf 'SHA256:  %s.sha256\n' "$archive_path"