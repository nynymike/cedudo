# Demo service: administrator guide

**Audience: the workshop administrator or facilitator.** Students never run
anything on this page. Student exercises are in `workshop-overview.md`.

`cedar-demo.service` is the real, harmless systemd service that Cedudo's
`read-logs` and `restart-demo` operations act on.

## What it is

- Program: `demo-service/cedar-demo` (installed to `/opt/cedar-demo/cedar-demo`, `root:root 0755`)
- Unit: `demo-service/cedar-demo.service` (installed to `/etc/systemd/system/`, `root:root 0644`)
- Account: system user and group `cedar-demo`, shell `/usr/sbin/nologin`, no home
- Behavior: logs `startup`, a `heartbeat` every 15 seconds, and `shutdown` on
  SIGTERM. Every line carries a `startup_id` unique to that run.
- No network ports, no external services, no state.

The unit file comments explain each restriction (`PrivateNetwork`,
`NoNewPrivileges`, `ProtectSystem=strict`, syscall filter, and so on).

## Assumptions about the VM

- Ubuntu 24.04 LTS with systemd running as init and the system Python 3
  (`/usr/bin/python3`), plus `/usr/bin/systemctl` and `/usr/bin/journalctl`.
  This is the only supported environment; the installer refuses anything else.
- An ordinary container without systemd does not qualify. Use a VM.
- Cedudo is already installed (see `README.md` steps 1 to 6) with the starter policy deployed.
- `alice` and `bob` are ordinary users: not in `sudo`, `admin`, `adm` or
  `systemd-journal`, and no polkit rule lets them manage services. That is why
  their direct `systemctl restart` fails; `--no-ask-password` makes it fail
  immediately instead of prompting.

## Install (root)

```bash
tools/install-demo-service.sh --check    # preflight only, changes nothing
sudo tools/install-demo-service.sh       # safe to rerun
sudo install -o root -g root -m 0644 operations.json /opt/cedudo/operations.json
```

The installer verifies the platform and tools, creates the account if needed
(refusing to reuse a login-capable or non-system account), installs the files
with explicit ownership and modes, reloads systemd, enables and starts the
service, and confirms it is active as `cedar-demo` and has logged a startup
line. A rerun restarts the service only if the installed files changed.

Quick check, as any user:

```bash
systemctl status cedar-demo --no-pager
```

## Validate (root)

```bash
sudo tools/test-demo-service.sh            # add --strict to fail on skips
```

Read the final `RESULT:` line. The script exits 0 for `PASSED WITH SKIPS`,
which is not a full pass: outside the business-hours window it skips the
allowed-restart check. `--strict` turns any skip into a failure. See
"Business-hours testing: choose how" below.

It checks ownership and permissions, no listening ports, journal output, a
denied and an allowed Cedudo restart (`InvocationID` and `startup_id` compared
before and after), trailing arguments, `restart-ssh` staying simulated, and
`root-shell` rejection. It restarts `cedar-demo` only, never SSH. Static checks
that need no VM: `python3 -m unittest discover -s tests`.

## Business-hours testing: choose how

`forbid-restart-outside-hours` forbids every `restart` request when the
`America/Chicago` hour is before 09:00 or at or after 17:00, on any day of the
week. It does not affect `read-logs`. Cedudo reads the system clock itself;
students cannot change the clock or the policy, and this guide does not weaken
the policy. **Do not change the VM clock as a routine installation workaround.**
Pick one of these three, in this order of preference.

| | Choice | What it proves | Changes the system? |
| --- | --- | --- | --- |
| 1 | Test `read-logs` and the after-hours denial now | Install works; the real forbid policy fires; denied restart leaves the service untouched | No |
| 2 | Explore an allowed daytime decision with the simulator | The policy *would* allow `bob` at 10:00 | No (never executes anything) |
| 3 | Run the real allowed-restart check during the window | Authorized restart really happens: new `InvocationID` and startup entry | No (just wait for 09:00 to 16:59 Central) |

### 1. Test now, outside the window

```bash
sudo ./tools/test-demo-service.sh
```

Outside the window the script skips the allowed-restart check, verifies that
`bob` is denied by `forbid-restart-outside-hours` with the service unchanged,
and ends `RESULT: PASSED WITH SKIPS`. That is a valid result for this choice,
but the allowed path is not verified. Also as the students would:

```bash
sudo -iu bob
cedudo explain restart-demo     # DENY, determining policy: forbid-restart-outside-hours
cedudo read-logs                # PERMIT regardless of the hour
exit
```

### 2. Simulate an allowed daytime decision

The simulator is unprivileged, never executes anything, and lets you supply the
hour. Run it from your clone with the **virtual environment's interpreter**.
The script's `#!/usr/bin/env python3` line would pick the system Python, which
does not have `cedarling_python`:

```bash
cd ~/cedudo
/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py restart-demo \
    --user bob --uid 1001 --gid 1001 --groups operators \
    --hour 10 --day-of-week 2 --is-weekend false \
    --policy-store /opt/cedudo/cedudo.cjar
```

Expect `ALLOW` with `operators-restart`. Change `--hour 22` to see
`forbid-restart-outside-hours`. Using `--policy-store /opt/cedudo/cedudo.cjar`
evaluates the archive actually deployed on this VM; omit it to evaluate the
clone's `policy/cedudo.cjar`. A simulated allow is not evidence that the real
restart works. Only choice 3 proves that.

### 3. Run the real check during the window

Between 09:00 and 16:59 `America/Chicago`, check and run:

```bash
TZ=America/Chicago date '+%A %H:%M'
sudo ./tools/test-demo-service.sh --strict
```

`--strict` fails if anything was skipped, so a pass means the allowed restart
produced a new `InvocationID` and a new `startup_id` in the journal.

### Last resort: pin the clock (isolated, disposable VM only)

Only if you must run choice 3 outside the window **and** this VM is a throwaway
used for nothing else. Do not do this on a VM that also uses OIDC login,
TLS/certificate validation, package installation, or anything with a real
identity: certificates, tokens and device codes are time-checked, journald
timestamps will jump, and a wrong clock can lock logins out.

1. Take a hypervisor snapshot first, so you can revert instead of repairing.
2. Disconnect nothing else; just pin, test, and restore:

```bash
sudo timedatectl set-ntp false
sudo date -s "@$(TZ=America/Chicago date -d 'today 10:00' +%s)"   # 10:00 Central today
sudo ./tools/test-demo-service.sh --strict
sudo timedatectl set-ntp true                                       # restore
timedatectl status                                                  # confirm synchronized
```

If anything fails midway, run the restore command before troubleshooting, or
revert the snapshot. Never leave a pinned clock on a VM students will use.

## Uninstall (root)

```bash
sudo tools/uninstall-demo-service.sh
```

Stops and disables the service and removes the unit, `/opt/cedar-demo`, and the
`cedar-demo` account and group only if the installer created them. It never
touches `/opt/cedudo`, `alice`, `bob`, or the `developers` and `operators`
groups.
