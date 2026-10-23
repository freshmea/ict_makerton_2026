#!/usr/bin/env python3
"""Collect a Jetson inventory as JSON using the Python standard library.

Run on the board: python3 -B collect_board_info.py > board-info.json
No sudo, package installation, service changes, camera capture or audio playback.
Passwords, environment variables, MAC addresses and hardware serials are excluded.
Each probe records its command, exit status, stdout and stderr independently.
"""

import datetime
import json
import os
import signal
import subprocess


PROBES = [
    ("identity", r"""
hostname
uname -a
printf '\nDevice tree model:\n'
tr '\0' '\n' < /proc/device-tree/model
printf '\nCompatible:\n'
tr '\0' '\n' < /proc/device-tree/compatible
for f in /proc/device-tree/nvidia,dtsfilename /proc/device-tree/nvidia,boardids; do
    if [ -r "$f" ]; then printf '\n%s:\n' "$f"; tr '\0' '\n' < "$f"; fi
done
"""),
    ("os", "cat /etc/os-release; cat /etc/nv_tegra_release; getconf GNU_LIBC_VERSION; ldd --version | head -n 1"),
    ("clock", "date --iso-8601=seconds; timedatectl show -p Timezone -p NTPSynchronized -p NTP; uptime; cat /proc/uptime"),
    ("cpu", "lscpu; printf '\\nCPU frequency kHz:\\n'; for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq; do if [ -r \"$f\" ]; then printf '%s: ' \"$f\"; cat \"$f\"; fi; done"),
    ("memory", "free -b; printf '\\nMeminfo:\\n'; cat /proc/meminfo; printf '\\nSwap devices:\\n'; swapon --show --bytes"),
    ("storage", r"""
lsblk --ascii -b -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL,TRAN,ROTA
printf '\nRoot mount:\n'
findmnt -n -o SOURCE,FSTYPE,OPTIONS /
df -B1 / /boot /home
printf '\nMMC non-unique attributes:\n'
for f in /sys/block/mmcblk*/device/name /sys/block/mmcblk*/device/type /sys/block/mmcblk*/device/date /sys/block/mmcblk*/device/manfid /sys/block/mmcblk*/device/oemid; do
    if [ -r "$f" ]; then printf '%s: ' "$f"; cat "$f"; fi
done
"""),
    ("network", "ip -4 -o addr show scope global; ip -4 route show default"),
    ("permissions", "id -un; id -Gn; printf '\\nDevice nodes:\\n'; find /dev -maxdepth 1 \\( -name 'ttyACM*' -o -name 'ttyUSB*' -o -name 'video*' -o -name 'gpiochip*' -o -name 'i2c-*' \\) -printf '%M %u %g %p\\n'; if [ -d /dev/snd ]; then ls -l /dev/snd; fi"),
    ("usb", "lsusb; printf '\\nUSB topology:\\n'; lsusb -t"),
    ("power_mode", "if command -v nvpmodel >/dev/null 2>&1; then nvpmodel -q; elif [ -x /usr/sbin/nvpmodel ]; then /usr/sbin/nvpmodel -q; else printf 'nvpmodel: not found\\n'; exit 127; fi"),
    ("thermal", "for d in /sys/class/thermal/thermal_zone*; do if [ -r \"$d/type\" ]; then printf '%s ' \"$d\"; cat \"$d/type\"; cat \"$d/temp\"; fi; done"),
    ("tegrastats", "if command -v tegrastats >/dev/null 2>&1; then timeout 3s tegrastats --interval 1000; else printf 'tegrastats: not found\\n'; exit 127; fi"),
    ("cuda", "printf 'CUDA directories:\\n'; ls -ld /usr/local/cuda* 2>/dev/null; for f in /usr/local/cuda/version.txt /usr/local/cuda/version.json; do if [ -r \"$f\" ]; then cat \"$f\"; fi; done; if command -v nvcc >/dev/null 2>&1; then nvcc --version; elif [ -x /usr/local/cuda/bin/nvcc ]; then /usr/local/cuda/bin/nvcc --version; else printf 'nvcc: not found\\n'; fi"),
    ("native_versions", "for p in glib-2.0 gstreamer-1.0 gstreamer-app-1.0 alsa opencv4 libudev; do printf '%s: ' \"$p\"; pkg-config --modversion \"$p\"; done; gst-launch-1.0 --version"),
    ("gstreamer_plugins", "GST_REGISTRY=/dev/null gst-inspect-1.0"),
    ("nvidia_plugin_libraries", r"""
for f in /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvarguscamerasrc.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvvidconv.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvv4l2camerasrc.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvvideo4linux2.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvcompositor.so; do
    printf '\nLIBRARY %s\n' "$f"
    if [ -r "$f" ]; then ls -l "$f"; ldd "$f"; else printf 'not found\n'; fi
done
"""),
    ("cuda_driver", r"""python3 -B - <<'PY'
import ctypes as c
import json
try:
    lib = c.CDLL('libcuda.so.1')
    result = {}
    status = lib.cuInit(0)
    result['cuInit'] = status
    if status == 0:
        version = c.c_int()
        result['cuDriverGetVersion'] = lib.cuDriverGetVersion(c.byref(version))
        result['driver_api_version'] = version.value
        count = c.c_int()
        result['cuDeviceGetCount'] = lib.cuDeviceGetCount(c.byref(count))
        result['device_count'] = count.value
        devices = []
        for ordinal in range(count.value):
            device = c.c_int()
            lib.cuDeviceGet(c.byref(device), ordinal)
            name = c.create_string_buffer(256)
            lib.cuDeviceGetName(name, len(name), device)
            major, minor = c.c_int(), c.c_int()
            lib.cuDeviceComputeCapability(c.byref(major), c.byref(minor), device)
            memory = c.c_size_t()
            lib.cuDeviceTotalMem_v2(c.byref(memory), device)
            devices.append({'name': name.value.decode(), 'compute_capability': [major.value, minor.value], 'total_memory_bytes': memory.value})
        result['devices'] = devices
    print(json.dumps(result, indent=2))
except OSError as e:
    print(str(e))
    raise SystemExit(1)
PY"""),
    ("opencv_python", r"""python3 -B - <<'PY'
import cv2
import numpy
print('cv2 version:', cv2.__version__)
print('cv2 path:', cv2.__file__)
print('numpy version:', numpy.__version__)
print('numpy path:', numpy.__file__)
for line in cv2.getBuildInformation().splitlines():
    if any(word in line for word in ('NVIDIA CUDA', 'cuDNN', 'GStreamer', 'FFMPEG', 'v4l/v4l2', 'NVIDIA GPU arch', 'NVIDIA PTX arch')):
        print(line)
PY"""),
    ("camera", "printf 'Video nodes:\\n'; find /dev -maxdepth 1 -name 'video*' -printf '%M %u %g %p\\n'; printf '\\nV4L device names:\\n'; for f in /sys/class/video4linux/*/name; do if [ -r \"$f\" ]; then printf '%s: ' \"$f\"; cat \"$f\"; fi; done"),
    ("audio_capture", "arecord -l"),
    ("audio_playback", "aplay -l"),
    ("tools", r"""
for p in python3 gcc g++ cmake make git pkg-config rustc cargo rustup node docker; do
    printf '\nTOOL %s\n' "$p"
    if command -v "$p" >/dev/null 2>&1; then command -v "$p"; "$p" --version 2>&1 | head -n 3; else printf 'not found in PATH\n'; fi
done
printf '\nRust home executables (version only):\n'
for p in "$HOME/.cargo/bin/rustc" "$HOME/.cargo/bin/cargo" "$HOME/.cargo/bin/rustup"; do
    if [ -x "$p" ]; then printf '%s\n' "$p"; "$p" --version 2>&1 | head -n 3; fi
done
"""),
    ("python_packages", "python3 -B -c 'import importlib.metadata as m, json; print(json.dumps(sorted([{\"name\": d.metadata.get(\"Name\", \"\"), \"version\": d.version} for d in m.distributions()], key=lambda d: d[\"name\"].lower()), indent=2))'"),
    ("debian_packages", "dpkg-query -W -f='${binary:Package}\\t${Version}\\t${Architecture}\\t${db:Status-Abbrev}\\n'"),
    ("project_services", "for p in picod controllerd camerad visiond audiod dialogued memoryd; do printf '\\n%s.service\\n' \"$p\"; systemctl show \"$p.service\" -p LoadState -p ActiveState -p UnitFileState --no-pager; done"),
]


def collect():
    result = {
        "schema_version": 1,
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "SSH inventory; no installation, reboot, recording or actuator commands",
        "probes": [],
    }
    for name, command in PROBES:
        probe = {"name": name, "command": command.strip()}
        try:
            p = subprocess.Popen(
                ["/bin/sh", "-c", command], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True,
                universal_newlines=True, errors="replace",
            )
            stdout, stderr = p.communicate(timeout=30)
            probe.update(exit_code=p.returncode, stdout=stdout, stderr=stderr)
        except subprocess.TimeoutExpired:
            # Stop only the process group created for this inventory probe.
            os.killpg(p.pid, signal.SIGKILL)
            stdout, stderr = p.communicate()
            probe.update(exit_code=None, error="timeout after 30 seconds",
                         stdout=stdout, stderr=stderr)
        result["probes"].append(probe)
    result["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return result


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
