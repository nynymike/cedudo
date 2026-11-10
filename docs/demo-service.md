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
allowed-restart check. `--strict` turns any skip into a failure.

It checks ownership and permissions, no listening ports, journal output, a
denied and an allowed Cedudo restart (`InvocationID` and `startup_id` compared
before and after), trailing arguments, `restart-ssh` staying simulated, and
`root-shell` rejection. It restarts `cedar-demo` only, never SSH. Static checks
that need no VM: `python3 -m unittest discover -s tests`.

## Business-hours window and the VM clock

`forbid-restart-outside-hours` forbids every `restart` request when the
`America/Chicago` hour is before 09:00 or at or after 17:00, on any day. It
does not affect `read-logs`. Cedudo reads the system clock itself, and students
cannot change it or the policy. To make the exercise predictable outside the
window, the administrator can pin the clock:

```bash
sudo timedatectl set-ntp false
sudo date -s 'TZ="America/Chicago" 2026-11-10 10:00:00'   # a weekday, 10:00 Central
# when finished:
sudo timedatectl set-ntp true
```

Do this only on a disposable workshop VM. The test script skips the allowed
restart check, and says so, when the clock is outside the window.

## Uninstall (root)

```bash
sudo tools/uninstall-demo-service.sh
```

Stops and disables the service and removes the unit, `/opt/cedar-demo`, and the
`cedar-demo` account and group only if the installer created them. It never
touches `/opt/cedudo`, `alice`, `bob`, or the `developers` and `operators`
groups.
