#!/usr/bin/env bash
set -euo pipefail

install_dir="/opt/kousen-remote"
device=""
start_service=1

usage() {
  cat <<'EOF'
Usage: sudo packaging/systemd/install-systemd.sh [options]

Options:
  --device ADDRESS       Bluetooth address or BlueZ path for the paired remote.
  --install-dir PATH     Install directory. Default: /opt/kousen-remote
  --no-start             Install and enable the service, but do not start it now.
  -h, --help             Show this help.

This script installs:
  /opt/kousen-remote
  /etc/default/kousen-remote
  /etc/systemd/system/kousen-remote.service
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device)
      device="${2:?missing value for --device}"
      shift 2
      ;;
    --install-dir)
      install_dir="${2:?missing value for --install-dir}"
      shift 2
      ;;
    --no-start)
      start_service=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo because this writes /opt, /etc/default, and /etc/systemd/system." >&2
  exit 1
fi

if [[ -z "${device}" ]]; then
  echo "Missing --device. Pass the paired remote Bluetooth address or BlueZ object path." >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "${script_dir}/../.." && pwd)"

echo "Installing kousen-remote from ${source_root}"
echo "Install directory: ${install_dir}"
echo "Remote device: ${device}"

apt-get update
apt-get install -y python3-venv python3-pip python3-dbus-next python3-evdev bluez

mkdir -p "${install_dir}"
tar \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./__pycache__' \
  --exclude='*/__pycache__' \
  -C "${source_root}" \
  -cf - . | tar -C "${install_dir}" -xf -

python3 -m venv --system-site-packages "${install_dir}/.venv"
"${install_dir}/.venv/bin/python" -m pip install --no-deps -e "${install_dir}"

install -m 0644 "${install_dir}/packaging/systemd/kousen-remote.service" /etc/systemd/system/kousen-remote.service
install -m 0644 "${install_dir}/packaging/systemd/kousen-remote.default" /etc/default/kousen-remote

escaped_device="$(printf '%s' "${device}" | sed 's/[&|]/\\&/g')"
escaped_mapping="$(printf '%s' "${install_dir}/mappings/kiosk-browser.json" | sed 's/[&|]/\\&/g')"
escaped_bin="$(printf '%s' "${install_dir}/.venv/bin/kousen-remote" | sed 's/[&|]/\\&/g')"

sed -i "s|^KOUSEN_REMOTE_DEVICE=.*|KOUSEN_REMOTE_DEVICE=${escaped_device}|" /etc/default/kousen-remote
sed -i "s|^KOUSEN_REMOTE_MAPPING=.*|KOUSEN_REMOTE_MAPPING=${escaped_mapping}|" /etc/default/kousen-remote
sed -i "s|/opt/kousen-remote/.venv/bin/kousen-remote|${escaped_bin}|" /etc/systemd/system/kousen-remote.service

systemctl daemon-reload
systemctl enable kousen-remote.service

if [[ "${start_service}" -eq 1 ]]; then
  systemctl restart kousen-remote.service
fi

systemctl --no-pager status kousen-remote.service || true
