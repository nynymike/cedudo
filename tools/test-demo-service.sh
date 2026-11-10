#!/usr/bin/env bash
# ADMINISTRATOR VALIDATION -- run as root on the Ubuntu 24.04 workshop VM,
# after tools/install-demo-service.sh and the Cedudo install (README.md):
#
#     sudo tools/test-demo-service.sh [--strict]
#
# Exit status 0 can mean "passed with skips". Read the RESULT line, or use
# --strict to make any skipped check a failure.
#
# This is an integration test. It needs real systemd, root, the installed
# cedudo wrapper, the deployed policy, and the users alice (developers) and
# bob (operators). It restarts cedar-demo.service. It does NOT restart ssh.
# Static checks that need none of that live in tests/test_static.py.
#
# The business-hours forbid policy (09:00-16:59 America/Chicago) applies to
# restart. Outside those hours the "allowed restart" test is SKIPPED and an
# after-hours denial is verified instead; the summary says which happened.
set -uo pipefail

SERVICE=cedar-demo.service
CEDUDO=/usr/local/bin/cedudo
PASS=0; FAIL=0; SKIP=0; STRICT=0
case "${1:-}" in
  "") ;;
  --strict) STRICT=1 ;;
  *) echo "usage: $0 [--strict]" >&2; exit 64 ;;
esac

[[ "${EUID}" -eq 0 ]] || { echo "error: run as root" >&2; exit 1; }

ok()   { PASS=$((PASS+1)); echo "PASS  $*"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL  $*"; }
skip() { SKIP=$((SKIP+1)); echo "SKIP  $*"; }
check() { # check "description" command...
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "${desc}"; else bad "${desc}"; fi
}

invocation() { systemctl show --property=InvocationID --value "${SERVICE}"; }
startup_id() {
  journalctl --unit="${SERVICE}" --output=cat --no-pager \
    | sed -n 's/^cedar-demo startup startup_id=\([0-9a-f]*\).*/\1/p' | tail -1
}
as() { local u="$1"; shift; runuser -u "${u}" -- "$@"; }
run_rc() { # run_rc VAR cmd... ; sets VAR to exit code, captures stdout in OUT
  local __var="$1"; shift
  local rc=0
  OUT="$("$@" 2>/dev/null)" || rc=$?
  printf -v "${__var}" '%s' "${rc}"
}

echo "== Service installation =="
check "service is active" systemctl is-active --quiet "${SERVICE}"
check "service is enabled" systemctl is-enabled --quiet "${SERVICE}"
pid="$(systemctl show --property=MainPID --value "${SERVICE}")"
[[ "$(ps -o user= -p "${pid}" | tr -d ' ')" == "cedar-demo" ]] \
  && ok "runs as unprivileged cedar-demo" || bad "runs as unprivileged cedar-demo"
[[ "$(getent passwd cedar-demo | cut -d: -f7)" =~ nologin|false ]] \
  && ok "account has no login shell" || bad "account has no login shell"
for f in /opt/cedar-demo/cedar-demo /etc/systemd/system/cedar-demo.service; do
  perm="$(stat -c '%U:%G %a' "${f}")"
  case "${perm}" in
    "root:root 755"|"root:root 644") ok "${f} ${perm}" ;;
    *) bad "${f} has ${perm}" ;;
  esac
done
for u in alice bob; do
  as "${u}" test -w /opt/cedar-demo/cedar-demo \
    && bad "${u} can write the service program" || ok "${u} cannot write the service program"
  as "${u}" test -w /etc/systemd/system/cedar-demo.service \
    && bad "${u} can write the unit" || ok "${u} cannot write the unit"
done
if command -v ss >/dev/null; then
  ss -H -tulnp 2>/dev/null | grep -q "pid=${pid}," \
    && bad "service has a listening socket" || ok "service listens on no ports"
fi

echo "== Journal =="
check "journal has startup message with startup_id" \
  bash -c "journalctl -u ${SERVICE} -o cat --no-pager | grep -q 'cedar-demo startup startup_id=[0-9a-f]'"

echo "== Direct restart as an unprivileged student =="
before="$(invocation)"
as alice systemctl --no-ask-password --no-pager restart "${SERVICE}" >/dev/null 2>&1
[[ $? -ne 0 ]] && ok "alice direct systemctl restart fails" || bad "alice direct systemctl restart fails"
[[ "$(invocation)" == "${before}" ]] && ok "direct restart left InvocationID unchanged" \
  || bad "direct restart changed InvocationID"

echo "== Denied Cedudo restart (alice, not in operators) =="
before="$(invocation)"; before_sid="$(startup_id)"
run_rc rc as alice "${CEDUDO}" restart-demo
[[ "${rc}" -eq 77 ]] && ok "alice restart-demo denied (exit 77)" || bad "alice restart-demo exit ${rc}, expected 77"
sleep 1
[[ "$(invocation)" == "${before}" && "$(startup_id)" == "${before_sid}" ]] \
  && ok "denied restart left InvocationID and startup_id unchanged" \
  || bad "denied restart changed the service"

echo "== Allowed Cedudo restart (bob, operators) =="
hour="$(TZ=America/Chicago date +%-H)"
before="$(invocation)"; before_sid="$(startup_id)"
if (( hour >= 9 && hour < 17 )); then
  run_rc rc as bob "${CEDUDO}" restart-demo
  [[ "${rc}" -eq 0 ]] && ok "bob restart-demo succeeded" || bad "bob restart-demo exit ${rc}"
  sleep 2
  after="$(invocation)"; after_sid="$(startup_id)"
  [[ -n "${after}" && "${after}" != "${before}" ]] && ok "new InvocationID after restart" || bad "InvocationID did not change"
  [[ -n "${after_sid}" && "${after_sid}" != "${before_sid}" ]] && ok "new startup_id in journal" || bad "startup_id did not change"
  check "service active after restart" systemctl is-active --quiet "${SERVICE}"
else
  skip "allowed restart needs 09:00-16:59 America/Chicago (now hour ${hour}); set the VM clock or rerun in hours"
  run_rc rc as bob "${CEDUDO}" restart-demo
  [[ "${rc}" -eq 77 ]] && ok "after hours: bob denied (forbid-restart-outside-hours)" || bad "after hours: bob exit ${rc}, expected 77"
  [[ "$(invocation)" == "${before}" ]] && ok "after-hours denial left InvocationID unchanged" || bad "after-hours denial changed the service"
fi

echo "== read-logs through Cedudo =="
run_rc rc as alice "${CEDUDO}" read-logs
[[ "${rc}" -eq 0 ]] && ok "alice read-logs succeeded" || bad "alice read-logs exit ${rc}"
grep -q 'cedar-demo startup startup_id=\|cedar-demo heartbeat' <<<"${OUT}" \
  && ok "read-logs shows cedar-demo messages" || bad "read-logs shows no cedar-demo messages"

echo "== Trailing arguments cannot change the command =="
run_rc rc as alice "${CEDUDO}" read-logs --unit=ssh.service --lines=500 -f
lines="$(grep -c . <<<"${OUT}")"
(( lines <= 21 )) && ok "extra journal options ignored (${lines} lines)" || bad "line limit exceeded (${lines})"
if grep -v '^-- ' <<<"${OUT}" | grep -vq 'cedar-demo'; then bad "output contains non-cedar-demo entries"; else ok "output only for cedar-demo"; fi
ssh_before="$(systemctl show --property=ActiveEnterTimestampMonotonic --value ssh.service)"
if (( hour >= 9 && hour < 17 )); then
  run_rc rc as bob "${CEDUDO}" restart-demo --no-ask-password restart ssh.service
  [[ "$(systemctl show --property=ActiveEnterTimestampMonotonic --value ssh.service)" == "${ssh_before}" ]] \
    && ok "trailing args did not restart ssh" || bad "ssh was restarted"
fi

echo "== Critical SSH resource (simulated) =="
run_rc rc as bob "${CEDUDO}" restart-ssh
[[ "${rc}" -eq 77 ]] && ok "bob restart-ssh denied by Cedar (exit 77)" || bad "restart-ssh exit ${rc}, expected 77"
[[ "$(systemctl show --property=ActiveEnterTimestampMonotonic --value ssh.service)" == "${ssh_before}" ]] \
  && ok "ssh service untouched" || bad "ssh service changed"

echo "== root-shell is not in the manifest =="
run_rc rc as bob "${CEDUDO}" root-shell
[[ "${rc}" -eq 77 ]] && ok "root-shell rejected" || bad "root-shell exit ${rc}"

echo
echo "Summary: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped"
if (( FAIL > 0 )); then
  echo "RESULT: FAILED"
  exit 1
fi
if (( SKIP > 0 )); then
  echo "RESULT: PASSED WITH SKIPS -- ${SKIP} check(s) did NOT run (see SKIP lines above)."
  echo "        The allowed-restart path is unverified. Rerun inside the business-hours window."
  (( STRICT == 1 )) && { echo "        --strict: treating skips as failure."; exit 1; }
  exit 0
fi
echo "RESULT: PASSED (nothing skipped)"
