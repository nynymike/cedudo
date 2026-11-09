#!/usr/bin/env bash
# ADMINISTRATOR CLEANUP -- run as root:  sudo tools/uninstall-demo-service.sh
#
# Removes only what tools/install-demo-service.sh created:
#   - cedar-demo.service (stopped, disabled, unit file deleted)
#   - /opt/cedar-demo/cedar-demo and its installer marker
#   - the "cedar-demo" user/group, ONLY if the installer created them
#
# It never touches /opt/cedudo, the cedudo wrapper, policies, alice, bob, or
# the developers/operators groups. Safe to rerun.
set -euo pipefail

SERVICE=cedar-demo
ACCOUNT=cedar-demo
INSTALL_DIR=/opt/cedar-demo
PROGRAM="${INSTALL_DIR}/cedar-demo"
UNIT=/etc/systemd/system/cedar-demo.service
MARKER="${INSTALL_DIR}/.installer-created-account"

die() { echo "error: $*" >&2; exit 1; }
info() { echo "==> $*"; }

[[ "${EUID}" -eq 0 ]] || die "run as root: sudo $0"

if systemctl cat "${SERVICE}.service" >/dev/null 2>&1; then
  info "stopping and disabling ${SERVICE}.service"
  systemctl stop "${SERVICE}.service" || true
  systemctl disable "${SERVICE}.service" || true
fi

rm -f "${UNIT}"
systemctl daemon-reload
systemctl reset-failed "${SERVICE}.service" 2>/dev/null || true
info "removed ${UNIT}"

# Read the marker before deleting it.
remove_user=0
remove_group=0
if [[ -f "${MARKER}" && ! -L "${MARKER}" ]]; then
  grep -qx 'user=1' "${MARKER}" && remove_user=1
  grep -qx 'group=1' "${MARKER}" && remove_group=1
fi

rm -f "${PROGRAM}" "${MARKER}"
# rmdir only succeeds when empty, so unrelated files are never deleted.
if [[ -d "${INSTALL_DIR}" ]]; then
  rmdir "${INSTALL_DIR}" 2>/dev/null \
    && info "removed ${INSTALL_DIR}" \
    || echo "note: ${INSTALL_DIR} not empty; left in place"
fi

if getent passwd "${ACCOUNT}" >/dev/null; then
  if [[ "${remove_user}" -eq 1 ]]; then
    # --force is not used: userdel refuses if the account has running processes.
    userdel "${ACCOUNT}"
    info "removed account ${ACCOUNT}"
  else
    echo "note: account ${ACCOUNT} was not created by the installer; left in place"
  fi
fi
if [[ "${remove_group}" -eq 1 ]] && getent group "${ACCOUNT}" >/dev/null; then
  groupdel "${ACCOUNT}" 2>/dev/null && info "removed group ${ACCOUNT}" \
    || echo "note: group ${ACCOUNT} already removed or still in use"
fi

info "cleanup complete"
