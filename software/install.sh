#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash software/install.sh'; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
test -x "$repo/software/target/release/nano-runtime"
id boarddash
systemctl stop 300seconds-runtime.target '300seconds-runtime@*.service' 2>/dev/null || true
systemctl disable --now 300seconds-dashboard.service
install -d -o root -g root -m 0755 /opt/300seconds/runtime
install -o root -g root -m 0755 "$repo/software/target/release/nano-runtime" /opt/300seconds/runtime/
install -o root -g root -m 0755 "$repo/software/workers/local_ai.py" /opt/300seconds/runtime/
install -o root -g root -m 0755 "$repo/software/tools/study.py" /opt/300seconds/runtime/
install -o root -g root -m 0755 "$repo/software/tools/calibrate.py" /opt/300seconds/runtime/
install -o root -g root -m 0755 "$repo/tools/pico-device-bench/target/release/pico-device-bench" /opt/300seconds/runtime/
# Keep the preserved diagnostic dashboard compatible with the v2 firmware.
if test -f /opt/300seconds/dashboard/pico-device-bench; then
  test -f /opt/300seconds/dashboard/pico-device-bench.v1 || cp -p /opt/300seconds/dashboard/pico-device-bench /opt/300seconds/dashboard/pico-device-bench.v1
  install -o root -g root -m 0755 "$repo/tools/pico-device-bench/target/release/pico-device-bench" /opt/300seconds/dashboard/pico-device-bench
fi
install -o root -g root -m 0644 "$repo/apps/device-dashboard/pico-config.json" /opt/300seconds/runtime/
test -f /opt/300seconds/runtime/actuators.json || install -o root -g root -m 0644 "$repo/software/config/actuators.json" /opt/300seconds/runtime/
install -o root -g root -m 0644 "$repo/software/deploy/300seconds-runtime@.service" "$repo/software/deploy/300seconds-runtime.target" /etc/systemd/system/
install -d -m 0755 /etc/systemd/system/300seconds-runtime@controllerd.service.d
printf '[Unit]\nAfter=300seconds-runtime@picod.service 300seconds-runtime@audiod.service\n' > /etc/systemd/system/300seconds-runtime@controllerd.service.d/order.conf
install -d -m 0755 /etc/systemd/system/300seconds-runtime@picod.service.d
# Keep legacy UDP backend inside picod's private loopback namespace. Other
# local processes must use the permission-checked Unix control/Stop sockets.
printf '[Service]\nPrivateNetwork=yes\n' > /etc/systemd/system/300seconds-runtime@picod.service.d/private-network.conf
install -d -m 0755 /etc/systemd/system/300seconds-runtime@dialogued.service.d
printf '[Service]\nEnvironmentFile=-/etc/300seconds/runtime.env\nEnvironmentFile=-/etc/300seconds/ai.env\n' > /etc/systemd/system/300seconds-runtime@dialogued.service.d/ai.conf
systemctl daemon-reload
echo 'Installed. No runtime auto-start. Start explicitly: sudo systemctl start 300seconds-runtime.target'
