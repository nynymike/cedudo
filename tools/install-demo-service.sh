#!/usr/bin/env bash
# ADMINISTRATOR SETUP -- run once on the workshop VM, as root:
#
#     sudo tools/install-demo-service.sh            # install (safe to rerun)
#     tools/install-demo-service.sh --check         # preflight only, changes nothing
#
# Installs cedar-demo.service, the harmless service that Cedudo's `read-logs`
# and `restart-demo` operations act on. Students never run this script.
#
# What it creates (and `tools/uninstall-demo-service.sh` removes):
#     /opt/cedar-demo/cedar-demo               root:root 0755  service program
#     /etc/systemd/system/cedar-demo.service   root:root 0644  unit file
#     user + group "cedar-demo"                system account, no login shell
set -euo pipefail

SERVICE=cedar-demo
ACCOUNT=cedar-demo
INSTALL_DIR=/opt/cedar-demo
PROGRAM="${INSTALL_DIR}/cedar-demo"
UNIT=/etc/systemd/system/cedar-demo.service
MARKER="${INSTALL_DIR}/.installer-created-account"
MANIFEST_INSTALLED=/opt/cedudo/operations.json

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_PROGRAM="${ROOT}/demo-service/cedar-demo"
SRC_UNIT="${ROOT}/demo-service/cedar-demo.service"
SRC_MANIFEST="${ROOT}/operations.json"

CHECK_ONLY=0
case "${1:-}" in
  "") ;;
  --check) CHECK_ONLY=1 ;;
  *) echo "usage: $0 [--check]" >&2; exit 64 ;;
esac

die() { echo "error: $*" >&2; exit 1; }
info() { echo "==> $*"; }

# --- 1. Verify the environment and dependencies -----------------------------
preflight() {
  [[ -r /etc/os-release ]] || die "cannot read /etc/os-release"
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
    die "supported platform is Ubuntu 24.04 (found ${PRETTY_NAME:-unknown})"
  fi
  [[ -d /run/systemd/system ]] || die "systemd is not the running init system"

  # The Cedudo manifest uses these exact absolute paths.
  local tool
  for tool in /usr/bin/systemctl /usr/bin/journalctl /usr/bin/python3; do
    [[ -x "${tool}" ]] || die "required program missing: ${tool}"
  done
  for tool in useradd getent install cmp; do
    command -v "${tool}" >/dev/null || die "required command missing: ${tool}"
  done
  [[ -f "${SRC_PROGRAM}" && -f "${SRC_UNIT}" ]] \
    || die "demo-service/ files not found under ${ROOT}"
}

# Warn (not fail) when the installed Cedudo manifest is not the repo version.
check_manifest() {
  if [[ ! -f "${MANIFEST_INSTALLED}" ]]; then
    echo "note: ${MANIFEST_INSTALLED} not found; install Cedudo first (README)."
  elif ! cmp -s "${SRC_MANIFEST}" "${MANIFEST_INSTALLED}"; then
    echo "WARNING: ${MANIFEST_INSTALLED} differs from ${SRC_MANIFEST}."
    echo "         Update it with:"
    echo "         sudo install -o root -g root -m 0644 ${SRC_MANIFEST} ${MANIFEST_INSTALLED}"
  fi
}

preflight
if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  check_manifest
  info "preflight OK (no changes made)"
  exit 0
fi
[[ "${EUID}" -eq 0 ]] || die "run as root: sudo $0"

# --- 2. Service account ------------------------------------------------------
mkdir -p "${INSTALL_DIR}"
[[ ! -L "${INSTALL_DIR}" ]] || die "${INSTALL_DIR} must not be a symlink"
created_user=0
created_group=0
if getent passwd "${ACCOUNT}" >/dev/null; then
  shell="$(getent passwd "${ACCOUNT}" | cut -d: -f7)"
  uid="$(getent passwd "${ACCOUNT}" | cut -d: -f3)"
  case "${shell}" in
    /usr/sbin/nologin|/sbin/nologin|/bin/false|/usr/bin/false) ;;
    *) die "existing account ${ACCOUNT} has login shell ${shell}; refusing to reuse" ;;
  esac
  [[ "${uid}" -lt 1000 ]] \
    || die "existing account ${ACCOUNT} is not a system account (uid ${uid})"
  info "service account ${ACCOUNT} already exists"
else
  info "creating system account ${ACCOUNT} (no login, no home)"
  if getent group "${ACCOUNT}" >/dev/null; then
    useradd --system --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin --gid "${ACCOUNT}" "${ACCOUNT}"
  else
    useradd --system --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin --user-group "${ACCOUNT}"
    created_group=1
  fi
  created_user=1
fi

# Install files first, then record what we created, so uninstall is precise.
# --- 3. Files, with explicit ownership and permissions -----------------------
install -d -o root -g root -m 0755 "${INSTALL_DIR}"
if [[ "${created_user}" -eq 1 ]]; then
  printf 'user=1\ngroup=%s\n' "${created_group}" > "${MARKER}"
  chown root:root "${MARKER}"
  chmod 0644 "${MARKER}"
fi

changed=0
if ! cmp -s "${SRC_PROGRAM}" "${PROGRAM}" 2>/dev/null \
   || ! cmp -s "${SRC_UNIT}" "${UNIT}" 2>/dev/null; then
  changed=1
fi
install -o root -g root -m 0755 "${SRC_PROGRAM}" "${PROGRAM}"
install -o root -g root -m 0644 "${SRC_UNIT}" "${UNIT}"
info "installed ${PROGRAM} (root:root 0755) and ${UNIT} (root:root 0644)"

# --- 4. systemd: reload, enable, start, verify -------------------------------
systemctl daemon-reload
systemctl enable "${SERVICE}.service"
if systemctl is-active --quiet "${SERVICE}.service"; then
  # Only restart on rerun when the installed files actually changed, so a
  # rerun during class does not disturb a running instance.
  if [[ "${changed}" -eq 1 ]]; then
    systemctl restart "${SERVICE}.service"
  fi
else
  systemctl start "${SERVICE}.service"
fi

ok=0
for _ in $(seq 1 20); do
  if systemctl is-active --quiet "${SERVICE}.service" \
     && journalctl --unit="${SERVICE}.service" --lines=20 --no-pager 2>/dev/null \
        | grep -q 'cedar-demo startup startup_id='; then
    ok=1
    break
  fi
  sleep 0.5
done
if [[ "${ok}" -ne 1 ]]; then
  systemctl status "${SERVICE}.service" --no-pager || true
  die "${SERVICE}.service did not start or wrote no startup message"
fi

pid="$(systemctl show --property=MainPID --value "${SERVICE}.service")"
owner="$(ps -o user= -p "${pid}" | tr -d ' ')"
[[ "${owner}" == "${ACCOUNT}" ]] \
  || die "service runs as '${owner}', expected '${ACCOUNT}'"

check_manifest
info "OK: ${SERVICE}.service is active as ${owner} (invocation $(systemctl show --property=InvocationID --value "${SERVICE}.service"))"
echo
echo "Next (administrator): install Cedudo and its manifest per README.md, then"
echo "validate with: sudo tools/test-demo-service.sh"
echo "Students then use: systemctl status cedar-demo --no-pager ; cedudo read-logs"
