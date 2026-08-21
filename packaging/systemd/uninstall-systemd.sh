#!/usr/bin/env bash
set -euo pipefail

install_dir="/opt/kousen-remote"

usage() {
  cat <<'EOF'
Usage: sudo packaging/systemd/uninstall-systemd.sh [options]

Options:
  --install-dir PATH     Install directory. Default: /opt/kousen-remote
  -h, --help             Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      install_dir="${2:?missing value for --install-dir}"
      shift 2
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
  echo "Run with sudo because this changes systemd files." >&2
  exit 1
fi

systemctl disable --now kousen-remote.service || true
rm -f /etc/systemd/system/kousen-remote.service
rm -f /etc/default/kousen-remote
systemctl daemon-reload

echo "Left installed files in ${install_dir}."
echo "Remove that directory manually if you no longer need the copied project files."
