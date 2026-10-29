#!/usr/bin/env bash
# Install on the Nano. Does not flash firmware or run actuator tests.
set -Eeuo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run with sudo bash apps/device-dashboard/install.sh'; exit 1; fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$source_dir/../.." && pwd)"
prefix=/opt/300seconds/dashboard
binary="$repo_dir/tools/pico-device-bench/target/release/pico-device-bench"
[[ -x "$binary" ]] || { echo "Build the native Rust bridge first: $binary"; exit 1; }
for group in audio video render robot-device dialout; do getent group "$group" >/dev/null || groupadd --system "$group"; done
id boarddash >/dev/null 2>&1 || useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin boarddash
usermod -aG audio,video,render,robot-device,dialout boarddash
export DEBIAN_FRONTEND=noninteractive
apt-get install -y ffmpeg python3.8-venv python3-gi python3-numpy python3-psutil python3-click python3-certifi gir1.2-gst-rtsp-server-1.0
install -d -m 0755 "$prefix/app" /etc/300seconds
python3.8 -m venv "$prefix/venv"
# Expose three distro packages, excluding unrelated global Python dependencies.
sed -i 's/include-system-site-packages = true/include-system-site-packages = false/' "$prefix/venv/pyvenv.cfg"
rm -f "$prefix/venv/lib/python3.8/site-packages/jetson-distro.pth"
for package in gi numpy psutil; do
    ln -sfn "/usr/lib/python3/dist-packages/$package" "$prefix/venv/lib/python3.8/site-packages/$package"
done
"$prefix/venv/bin/python" -m pip install --disable-pip-version-check 'pip==25.0.1'
"$prefix/venv/bin/python" -m pip install --disable-pip-version-check -r "$source_dir/requirements.txt"
"$prefix/venv/bin/python" -m pip check
systemctl stop 300seconds-dashboard.service 2>/dev/null || true
cp -a "$source_dir/." "$prefix/app/"
chown -R root:root "$prefix/app"
chmod -R u=rwX,go=rX "$prefix/app"
install -m 0755 "$binary" "$prefix/pico-device-bench"
[[ -e /etc/300seconds/dashboard.env ]] || install -m 0644 "$source_dir/dashboard.env.example" /etc/300seconds/dashboard.env
if ! grep -q '^LEARNING_AUTOSTART=' /etc/300seconds/dashboard.env; then
    printf '\nLEARNING_AUTOSTART=0\n' >> /etc/300seconds/dashboard.env
fi
install -m 0644 "$source_dir/300seconds-dashboard.service" /etc/systemd/system/300seconds-dashboard.service
install -d -m 0755 /etc/NetworkManager/dispatcher.d
install -m 0755 "$source_dir/90-300seconds-dashboard-wifi" /etc/NetworkManager/dispatcher.d/90-300seconds-dashboard-wifi
systemctl daemon-reload
systemctl enable --now 300seconds-dashboard.service
if [[ -x /opt/300seconds/runtime/nano-runtime ]]; then
    bash "$source_dir/install-tts.sh"
fi
if [[ -f "$repo_dir/tools/jetson/install-study-observer.sh" ]]; then
    bash "$repo_dir/tools/jetson/install-study-observer.sh"
fi
systemctl --no-pager status 300seconds-dashboard.service
