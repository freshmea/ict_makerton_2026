#!/usr/bin/env bash
# Run with sudo. Native dependencies are additive; no upgrade/autoremove.
set -Eeuo pipefail
export LC_ALL=C
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
TARGET_USER=${1:-${SUDO_USER:-jetson}}
RUST_VERSION=1.90.0
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
[[ $(uname -m) == aarch64 && -r /etc/nv_tegra_release ]] || {
    echo 'This installer is for an aarch64 Jetson.' >&2; exit 1;
}
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
[[ -n $TARGET_HOME && -d $TARGET_HOME ]] || { echo 'Unknown target user.' >&2; exit 1; }
install -d -m 0755 /var/log/300seconds
LOG=/var/log/300seconds/deps-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee -a "$LOG") 2>&1
echo "START $(date -u --iso-8601=seconds) user=$TARGET_USER"
echo "Log: $LOG"
dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Abbrev}\n' > "${LOG%.log}-packages-before.tsv"
packages=(
    build-essential cmake pkg-config git curl ca-certificates
    libssl-dev libudev-dev libasound2-dev libglib2.0-dev
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
    libsqlite3-dev libclang-dev
    gstreamer1.0-tools gstreamer1.0-plugins-base
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-alsa
    alsa-utils v4l-utils shellcheck
)
missing=()
for package in "${packages[@]}"; do
    if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]]; then
        missing+=("$package")
    fi
done
if ((${#missing[@]})); then
    # Use only signed Ubuntu Focal repositories for these Ubuntu dependencies.
    # Existing ROS/NVIDIA/vendor source files and signing keys are left intact.
    grep -q '^VERSION_ID="20.04"' /etc/os-release || { echo 'Expected Ubuntu 20.04.' >&2; exit 1; }
    install -d -m 0755 /var/lib/300seconds/dependencies
    APT_SOURCE_FILE=/var/lib/300seconds/dependencies/ubuntu-focal.list
    cat > "$APT_SOURCE_FILE" <<'SOURCES'
deb http://ports.ubuntu.com/ubuntu-ports focal main restricted universe multiverse
deb http://ports.ubuntu.com/ubuntu-ports focal-updates main restricted universe multiverse
deb http://ports.ubuntu.com/ubuntu-ports focal-security main restricted universe multiverse
SOURCES
    apt_options=(-o "Dir::Etc::sourcelist=$APT_SOURCE_FILE" -o 'Dir::Etc::sourceparts=-' -o 'APT::Get::List-Cleanup=0')
    apt-get "${apt_options[@]}" update
    apt-get "${apt_options[@]}" -s --no-install-recommends --no-upgrade --no-remove install "${missing[@]}" > "${LOG%.log}-apt-plan.txt"
    cat "${LOG%.log}-apt-plan.txt"
    if grep -Eq '^Remv |^Inst (nvidia-|cuda-|libcudnn|libnvinfer|libopencv|libglib2|libgstreamer|systemd|linux-image)' "${LOG%.log}-apt-plan.txt"; then
        echo 'Refusing a plan that removes packages or changes protected platform libraries.' >&2
        exit 1
    fi
    apt-get "${apt_options[@]}" -y --no-install-recommends --no-upgrade --no-remove install "${missing[@]}"
fi

# Keep the project Rust toolchain separate from existing user/global defaults.
RUST_BASE="$TARGET_HOME/.local/share/300seconds/rust"
install -d -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 0755 "$RUST_BASE"
as_user() {
    runuser -u "$TARGET_USER" -- env HOME="$TARGET_HOME" \
        CARGO_HOME="$RUST_BASE/cargo" RUSTUP_HOME="$RUST_BASE/rustup" \
        PATH="$RUST_BASE/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" "$@"
}
if [[ ! -x $RUST_BASE/cargo/bin/rustup ]]; then
    as_user curl --proto '=https' --tlsv1.2 --fail --location \
        --retry 3 https://sh.rustup.rs --output "$RUST_BASE/rustup-init.sh"
    sha256sum "$RUST_BASE/rustup-init.sh"
    as_user sh "$RUST_BASE/rustup-init.sh" -y --no-modify-path \
        --profile minimal --default-toolchain "$RUST_VERSION"
fi
as_user rustup toolchain install "$RUST_VERSION" --profile minimal --no-self-update
as_user rustup component add --toolchain "$RUST_VERSION" rustfmt clippy rust-analyzer
# Do not change shell startup files or the user's global rustup default.
# Variables in this quoted program intentionally expand in the target user's shell.
# shellcheck disable=SC2016
as_user bash -c 'printf "export CARGO_HOME=%q\nexport RUSTUP_HOME=%q\nexport PATH=\"%s:\$PATH\"\nexport RUSTUP_TOOLCHAIN=1.90.0\n" "$CARGO_HOME" "$RUSTUP_HOME" "$CARGO_HOME/bin" > "$1"' _ "$RUST_BASE/env.sh"
as_user rustc +"$RUST_VERSION" -Vv
as_user cargo +"$RUST_VERSION" --version
for package in openssl libudev alsa glib-2.0 gstreamer-1.0 gstreamer-app-1.0 sqlite3; do
    printf '%s: ' "$package"
    pkg-config --modversion "$package"
done
usermod -a -G dialout "$TARGET_USER"
RULE=/etc/udev/rules.d/90-pico-device.rules
EXPECTED_RULE='SUBSYSTEM=="tty", ATTRS{idVendor}=="c0de", ATTRS{idProduct}=="cafc", MODE="0660", GROUP="dialout", TAG+="uaccess", SYMLINK+="pico-device"'
if [[ -e $RULE ]] && ! grep -Fxq "$EXPECTED_RULE" "$RULE"; then
    echo "Preserving an existing different $RULE; configure the Pico rule manually." >&2
    exit 1
fi
if [[ ! -e $RULE ]]; then
    printf '# Pico binary device bench; no port is opened by this rule.\n%s\n' "$EXPECTED_RULE" > "$RULE"
    chmod 0644 "$RULE"
    udevadm control --reload-rules
fi
echo "User groups: $(id -nG "$TARGET_USER"). Reconnect SSH/VS Code for new dialout membership."
dpkg-query -W -f='${binary:Package}\t${Version}\t${db:Status-Abbrev}\n' > "${LOG%.log}-packages-after.tsv"
echo "FINISHED $(date -u --iso-8601=seconds)"
echo "Activate project Rust: source $RUST_BASE/env.sh"
