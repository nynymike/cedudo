# Tools reference

Manual-page style reference for every command, script and program in this
repository. For the narrative install, see [`README.md`](../README.md); for how
`cedudo` makes decisions, see [`cedudo.md`](cedudo.md); for the demo service,
see [`demo-service.md`](demo-service.md).

Paths are relative to the repository clone unless they start with `/`.

## At a glance

| Tool | Who runs it | Privilege | Changes the system? |
| --- | --- | --- | --- |
| [`cedudo`](#cedudo) | Students (`alice`, `bob`) | Setuid wrapper runs it as root | Only by running the fixed, authorized operation |
| [`cedudo-wrapper.c`](#cedudo-wrapperc-and-install-wrappersh) / [`install-wrapper.sh`](#cedudo-wrapperc-and-install-wrappersh) | Administrator | No `sudo` on the command; script calls `sudo` | Yes: installs the setuid wrapper and symlink |
| [`tools/build-cjar.sh`](#toolsbuild-cjarsh) | Administrator or policy author | No `sudo` | Writes `policy/cedudo.cjar` in the clone |
| [`tools/deploy-policy.sh`](#toolsdeploy-policysh) | Administrator | No `sudo` on the command; script calls `sudo` | Yes: installs `/opt/cedudo/cedudo.cjar` |
| [`tools/serve-policy.py`](#toolsserve-policypy) | Anyone | None | Opens a local HTTP port |
| [`tools/cedudo-simulate.py`](#toolscedudo-simulatepy) | Anyone | None | No (never executes anything) |
| [`tools/install-demo-service.sh`](#toolsinstall-demo-servicesh) | Administrator | `sudo` (root) | Yes, except with `--check` |
| [`tools/uninstall-demo-service.sh`](#toolsuninstall-demo-servicesh) | Administrator | `sudo` (root) | Yes |
| [`tools/test-demo-service.sh`](#toolstest-demo-servicesh) | Administrator | `sudo` (root) | Restarts `cedar-demo.service` |
| [`tests/test_static.py`](#teststest_staticpy) | Anyone | None | No |
| [`demo-service/cedar-demo`](#demo-servicecedar-demo) | systemd | `cedar-demo` account | No |

---

## cedudo

### NAME

`cedudo` - Cedar-authorized privilege wrapper (a restrictive `sudo`)

### SYNOPSIS

```text
cedudo <operation-id>
cedudo explain <operation-id>
cedudo --help
```

### DESCRIPTION

Runs one fixed, root-owned operation if a Cedar policy allows it. The caller
supplies only an operation ID. The executable and every argument come from the
root-owned manifest `/opt/cedudo/operations.json`. Authorization is evaluated
locally by Cedarling against `/opt/cedudo/cedudo.cjar`. Any configuration,
Cedarling or evaluation error fails closed: nothing is executed.

The invoking user is taken from the **real** uid, resolved through the account
database, with groups from `os.getgrouplist`. `cedudo` refuses to run for root
(`direct root invocation is not a workshop principal`) because it authorizes
the original Linux user.

Installed form: `/usr/local/bin/cedudo` -> `/opt/cedudo/cedudo` (setuid-root C
wrapper) -> `/opt/cedudo/venv/bin/python3 /opt/cedudo/cedudo.py`.

`cedudo --help` prints the full built-in manual, including the context fields
and policy-writing examples, and works for any user without the setuid install.

### OPERATIONS (shipped manifest)

| Operation ID | Cedar action | Cedar resource | Execution |
| --- | --- | --- | --- |
| `read-logs` | `Linux::Action::"read-logs"` | `Linux::Service::"cedar-demo"` | Real: `/usr/bin/journalctl --unit=cedar-demo.service --lines=20 --no-pager --output=short-iso` |
| `restart-demo` | `Linux::Action::"restart"` | `Linux::Service::"cedar-demo"` | Real: `/usr/bin/systemctl --no-ask-password --no-pager restart cedar-demo.service` |
| `restart-ssh` | `Linux::Action::"restart"` | `Linux::Service::"ssh"` (critical) | Simulated: `/usr/bin/echo` prints a message; SSH is never restarted |

An ID must match `[a-z][a-z0-9-]{0,63}`. An ID not in the manifest (for example
`root-shell`) is rejected before Cedar runs.

### OPTIONS

`-h`, `--h`, `--help`, `help`
: Print the manual and exit 0. Recognized anywhere in the arguments.

`explain <operation-id>`
: Dry run. Prints the real identity (real and effective uid/gid, groups), the
  Cedar action and resource, every context value with its source, the
  policy-store fingerprint, the decision with determining policy IDs and any
  evaluation errors, and the argv that *would* run. Never executes the
  operation.

Extra arguments after the operation ID are logged as a warning and ignored.
They cannot change the executed command.

### ENVIRONMENT

The caller's environment is not passed to the operation. The child gets only:
`PATH=/usr/sbin:/usr/bin:/sbin:/bin`, `HOME=/root`, `USER=root`,
`LOGNAME=root`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, `TERM=dumb`, `PAGER=cat`,
`SYSTEMD_PAGER=cat`. The working directory is `/` and the umask `022`.
`CEDARLING_*` variables are removed before Cedarling is configured.

A few context fields are read from the caller's environment and are advisory
only (forgeable): `login_source_ip` (`SSH_CONNECTION`, `SSH_CLIENT`) and
`auth_method` (`PAM_*`, `SSH_AUTH_INFO_0`).

### FILES

| File | Purpose |
| --- | --- |
| `/usr/local/bin/cedudo` | Symlink to the wrapper |
| `/opt/cedudo/cedudo` | Setuid-root wrapper, `root:root 4755` |
| `/opt/cedudo/cedudo.py` | The program |
| `/opt/cedudo/operations.json` | Operation manifest (must be a root-owned regular file, not group/world writable) |
| `/opt/cedudo/cedudo.cjar` | Cedar policy archive (same trust rules) |
| `/opt/cedudo/venv/` | Python environment with `cedarling-python` |

Each manifest executable must be an absolute path, a root-owned regular file,
not group/world writable, and executable.

### EXIT STATUS

| Code | Meaning |
| --- | --- |
| 0 | Authorized command executed (it replaces `cedudo`), or `explain`/help finished. The exit status of an executed command is **its own**. |
| 64 | Usage error (bad or missing operation ID) |
| 69 | Cedarling initialization or evaluation error, or group lookup failure (service unavailable) |
| 70 | The authorized command could not be started |
| 77 | Denied by policy, unknown operation, or not permitted (including an unknown calling user and root) |
| 78 | Configuration error (untrusted manifest, archive or executable) |

A permitted request can still fail inside the command (for example a
`systemctl` error). That failure is the command's, not Cedar's.

### EXAMPLES

```bash
sudo -iu alice
cedudo read-logs
cedudo explain restart-demo
exit
```

### SEE ALSO

[`cedudo.md`](cedudo.md), `cedudo --help`, [`cedudo-simulate.py`](#toolscedudo-simulatepy)

---

## cedudo-wrapper.c and install-wrapper.sh

### NAME

`cedudo-wrapper.c` - setuid C launcher; `install-wrapper.sh` - builds and
installs it

### SYNOPSIS

```bash
./install-wrapper.sh
```

Run from the repository root, as your administrator account, **without
`sudo`**.

### DESCRIPTION

Linux ignores the setuid bit on interpreted scripts, so a small compiled
program carries it. `cedudo-wrapper.c` does one thing: `execv` of the fixed
path `/opt/cedudo/venv/bin/python3` with `/opt/cedudo/cedudo.py` and the
caller's arguments. The Python and script paths are compiled in and cannot be
changed by the caller.

`install-wrapper.sh` then:

1. compiles `cedudo-wrapper.c` to `./cedudo-wrapper` with `gcc` (as you);
2. `sudo cp` to `/opt/cedudo/cedudo`, `sudo chown root:root`, `sudo chmod 4755`;
3. `sudo ln -sf /opt/cedudo/cedudo /usr/local/bin/cedudo`;
4. removes the local `cedudo-wrapper` build artifact.

It secures only the wrapper and the symlink. The venv, `cedudo.py`, the
manifest and the archive are installed and checked separately (README steps 3
to 5 and "Verify").

### PREREQUISITES

`gcc`, `sudo`, and an existing `/opt/cedudo` directory (README step 2). If run
as root it prints a note advising an administrator account instead.

### EXIT STATUS

Non-zero if any step fails (the script uses `set -e`).

### EXAMPLES

```bash
chmod +x install-wrapper.sh
./install-wrapper.sh
stat -c '%U:%G %a' /opt/cedudo/cedudo      # root:root 4755
```

Rerun it to repair a missing or wrong wrapper; there is no separate manual
recipe.

---

## tools/build-cjar.sh

### NAME

`build-cjar.sh` - package the policy store into a Cedar Archive

### SYNOPSIS

```bash
./tools/build-cjar.sh
```

No options. Run as an ordinary user (it writes into the clone).

### DESCRIPTION

Zips `policy/store/` into `policy/cedudo.cjar`. It is **packaging, not full
validation**. It checks that:

- `policy/store/metadata.json`, `schema.cedarschema` and `schema.json` exist;
- `policy/store/policies/` contains at least one file;
- `metadata.json` has the keys `cedar_version` and `policy_store`, and
  `policy_store` has `id` and `name`, with `id` a hexadecimal string of 15 to
  64 characters;
- each `policies/*.cedar` file contains exactly one `@id("...")` annotation.

It does **not** parse the Cedar policies or check them against the schema. A
policy error appears when Cedarling loads the archive. `.DS_Store` files and
`.git` directories are excluded. The existing archive is removed and rebuilt,
which changes the tracked file's zip timestamps.

### PREREQUISITES

`bash`, `python3`, `zip`. (`zip` is checked up front.)

### FILES

| File | Role |
| --- | --- |
| `policy/store/` | Input: metadata, schema files, `policies/`, `entities/` |
| `policy/cedudo.cjar` | Output |

### EXIT STATUS

0 on success; 1 on any failed check; a metadata error exits non-zero with a
message.

### SEE ALSO

[`tools/deploy-policy.sh`](#toolsdeploy-policysh)

---

## tools/deploy-policy.sh

### NAME

`deploy-policy.sh` - install the policy archive for enforcement

### SYNOPSIS

```bash
./tools/deploy-policy.sh
```

No options. Run as your administrator account; the script calls `sudo` itself.

### DESCRIPTION

Validates `policy/cedudo.cjar`, then installs it as `/opt/cedudo/cedudo.cjar`
with `sudo mkdir -p /opt/cedudo`, `sudo cp`, `sudo chown root:root` and
`sudo chmod 0644`. Validation requires that the file exists, is a valid ZIP
(`unzip -t`), and lists `metadata.json`, `schema.cedarschema`, `schema.json`
and a `policies/` entry. Like `build-cjar.sh`, this checks archive structure,
not policy correctness.

### PREREQUISITES

`unzip`, `sudo`, and a built `policy/cedudo.cjar` (run `build-cjar.sh` first).

### EXIT STATUS

0 on success; 1 if the archive is missing or fails a check.

### EXAMPLES

```bash
./tools/build-cjar.sh
./tools/deploy-policy.sh
sudo -iu alice
cedudo explain read-logs
exit
```

---

## tools/serve-policy.py

### NAME

`serve-policy.py` - serve the policy directory to Tarp over HTTP with CORS

### SYNOPSIS

```bash
python3 tools/serve-policy.py
```

No options. Stop with Ctrl-C.

### DESCRIPTION

Starts a static file server on **127.0.0.1:8000** (loopback only) rooted at
`policy/`, adding `Access-Control-Allow-Origin: *` and answering `OPTIONS` so a
browser extension can load the archive. Point Tarp at
`http://127.0.0.1:8000/cedudo.cjar`.

It serves everything under `policy/`, including `samples/` and `store/`. The
port and bind address are fixed in the source. If port 8000 is busy it fails
with an OSError.

### EXIT STATUS

1 if `policy/` does not exist; otherwise runs until interrupted.

---

## tools/cedudo-simulate.py

### NAME

`cedudo-simulate.py` - unprivileged Cedar decision simulator

### SYNOPSIS

```bash
/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py <operation-id> [options]
```

### DESCRIPTION

Evaluates a request with a **synthetic** identity and context overrides, and
prints the decision. It is not setuid, is not installed to `/opt/cedudo`, and
never executes the operation. Use it for "what if" questions that `cedudo
explain` cannot answer, such as "what if bob ran this at 10:00?". Keeping the
overrides out of the setuid program means no one can use them to influence a
real decision.

**Use the venv interpreter.** The script starts with `#!/usr/bin/env python3`,
which picks the system Python, where `cedarling_python` is not installed.
Running it as `/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py ...` works
for any user who can read the clone and `/opt/cedudo/venv`. The simulator needs
Python 3.9 or later (`zoneinfo`).

The default context is a local, interactive, low-risk session at the current
time in `America/Chicago`. `--local-console` and `--is-remote` are kept
consistent if only one is given.

### OPTIONS

Positional:

`operation-id`
: An ID from the operations file.

Files:

`--operations PATH`
: Manifest to read. Default: `operations.json` in the clone.

`--policy-store PATH`
: Archive to evaluate. Default: `policy/cedudo.cjar` in the clone. Use
  `/opt/cedudo/cedudo.cjar` to evaluate what is deployed.

Synthetic identity:

| Option | Default |
| --- | --- |
| `--user NAME` | `alice` |
| `--uid N` | `1000` |
| `--gid N` | `1000` |
| `--groups A,B` | `developers` (comma-separated) |
| `--home PATH` | `/home/<user>` |
| `--shell PATH` | `/bin/bash` |

Context overrides (each replaces one context field):

`--current-time N`, `--hour N`, `--day-of-week N` (ISO 1 to 7),
`--is-weekend BOOL`, `--date YYYY-MM-DD`, `--hostname S`,
`--intruder-risk-level S`, `--local-console BOOL`, `--is-remote BOOL`,
`--interactive BOOL`, `--tty S`, `--session-age-seconds N`,
`--login-source-ip IP`, `--auth-method S`.

Booleans accept `true/false`, `t/f`, `yes/no`, `y/n`, `1/0`.

### OUTPUT

The identity, Cedar action and resource, every context value, the policy store
path and fingerprint, then `result : ALLOW|DENY`, the determining policy IDs
and any evaluation errors. A simulated allow is not proof that the real
command works.

### EXIT STATUS

0 after printing a decision; 2 if `cedarling_python` is missing; otherwise
exits with an `error:` message (unknown operation, missing archive, Cedarling
initialization or evaluation failure).

### EXAMPLES

```bash
# bob (operators) at 10:00: expect ALLOW via operators-restart
/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py restart-demo \
    --user bob --uid 1001 --gid 1001 --groups operators \
    --hour 10 --day-of-week 2 --is-weekend false \
    --policy-store /opt/cedudo/cedudo.cjar

# the same at 22:00: expect DENY via forbid-restart-outside-hours
/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py restart-demo \
    --user bob --groups operators --hour 22
```

---

## tools/install-demo-service.sh

### NAME

`install-demo-service.sh` - install and start `cedar-demo.service`

### SYNOPSIS

```bash
tools/install-demo-service.sh --check
sudo tools/install-demo-service.sh
```

### DESCRIPTION

Administrator setup for the demo service. Safe to rerun.

`--check` runs the preflight only and changes nothing. It can run without
root. It verifies Ubuntu 24.04, a running systemd, `/usr/bin/systemctl`,
`/usr/bin/journalctl`, `/usr/bin/python3`, and the commands `useradd`,
`getent`, `install` and `cmp`, and that the `demo-service/` files exist. It
also warns if `/opt/cedudo/operations.json` differs from the repository copy.
**It is not a Cedudo installation check**: it does not verify the venv, the
wrapper, file ownership, the archive or the users.

Without `--check` (as root) it:

1. runs the preflight;
2. creates the system account and group `cedar-demo` (`--system`, no home,
   `/usr/sbin/nologin`) if needed. It refuses to reuse an existing
   `cedar-demo` account that has a login shell or a non-system uid;
3. installs `/opt/cedar-demo/cedar-demo` (`root:root 0755`) and
   `/etc/systemd/system/cedar-demo.service` (`root:root 0644`);
4. records in `/opt/cedar-demo/.installer-created-account` whether it created
   the user and group, so uninstall removes only those;
5. `systemctl daemon-reload`, `enable`, and `start` (or `restart`, only if the
   installed files changed);
6. waits up to about 10 seconds for the service to be active and to have logged
   a `cedar-demo startup startup_id=` line, and checks that it runs as
   `cedar-demo`.

### EXIT STATUS

0 on success; 1 on a failed check or verification (message on stderr); 64 for a
bad option.

### FILES

`/opt/cedar-demo/cedar-demo`, `/etc/systemd/system/cedar-demo.service`,
`/opt/cedar-demo/.installer-created-account`

### SEE ALSO

[`demo-service.md`](demo-service.md)

---

## tools/uninstall-demo-service.sh

### NAME

`uninstall-demo-service.sh` - remove only what the demo installer created

### SYNOPSIS

```bash
sudo tools/uninstall-demo-service.sh
```

### DESCRIPTION

Stops and disables `cedar-demo.service`, deletes its unit file, reloads systemd,
removes `/opt/cedar-demo/cedar-demo` and the installer marker, and removes
`/opt/cedar-demo` with `rmdir` (so it is left alone if it holds anything
else). It deletes the `cedar-demo` user and group **only** if the marker says
the installer created them, and never forces removal while the account has
running processes.

It never touches `/opt/cedudo`, the `cedudo` wrapper, policies, `alice`, `bob`,
or the `developers` and `operators` groups. Safe to rerun.

### EXIT STATUS

0 on success; 1 if not run as root or on an error.

---

## tools/test-demo-service.sh

### NAME

`test-demo-service.sh` - VM integration checks for the demo service and Cedudo

### SYNOPSIS

```bash
sudo tools/test-demo-service.sh [--strict]
```

### DESCRIPTION

Integration test for the Ubuntu 24.04 workshop VM. It needs root, real systemd,
the installed `cedudo` (`/usr/local/bin/cedudo`), the deployed starter policy,
and the users `alice` (developers) and `bob` (operators). Students are run via
`runuser`. It restarts `cedar-demo.service`; it never restarts SSH.

It checks, in order:

- **Installation:** service active and enabled; runs as `cedar-demo`; no login
  shell; owner and mode of the program and unit; `alice` and `bob` cannot write
  them; no listening sockets.
- **Journal:** a startup line with a `startup_id`.
- **Direct restart:** `alice`'s `systemctl --no-ask-password restart` fails and
  leaves the `InvocationID` unchanged.
- **Denied Cedudo restart:** `alice` gets exit 77; `InvocationID` and
  `startup_id` unchanged.
- **Allowed Cedudo restart:** `bob` succeeds; a new `InvocationID` and
  `startup_id` appear; the service is active. This needs 09:00 to 16:59
  `America/Chicago`. Outside it the check is **skipped** and an after-hours
  denial is verified instead.
- **`read-logs`:** `alice` gets cedar-demo journal output.
- **Trailing arguments:** extra journal options are ignored (line count
  bounded, only cedar-demo entries), and extra arguments do not restart SSH.
- **Simulated SSH:** `restart-ssh` is denied and the SSH service is unchanged.
- **`root-shell`:** rejected.

### OPTIONS

`--strict`
: Treat skipped checks as failure.

### EXIT STATUS

| Code | Meaning |
| --- | --- |
| 0 | `RESULT: PASSED (nothing skipped)`, or `PASSED WITH SKIPS` without `--strict` |
| 1 | `RESULT: FAILED`, skips under `--strict`, or not run as root |
| 64 | Bad option |

**Exit 0 can include skips.** Read the final `RESULT:` line.

### SEE ALSO

[`demo-service.md`](demo-service.md) (business-hours testing choices)

---

## tests/test_static.py

### NAME

`test_static.py` - static and mocked checks; no root, systemd or Cedarling

### SYNOPSIS

```bash
python3 -m unittest discover -s tests
python3 -m unittest discover -s tests -v      # list each test
```

### DESCRIPTION

`unittest` checks that run anywhere with Python 3.9 or later. They cover the
manifest operation IDs, exact arguments and Cedar mappings; that `restart-ssh`
stays simulated; consistency between documentation, help text and the manifest
(including no stale `cedudo restart` or `view-logs`); the README structure and
install commands; the demo program's messages, unique startup IDs and clean
SIGTERM exit; the unit file settings; shell syntax of the scripts (and
`shellcheck` if installed); and mocked `cedudo` behavior showing that trailing
arguments and the caller's environment cannot change the executed command, and
that a denial executes nothing. `cedarling_python` is stubbed.

They do **not** prove the VM works. Service installation, startup, the real
restart and the `InvocationID` comparison are covered only by
[`tools/test-demo-service.sh`](#toolstest-demo-servicesh).

### EXIT STATUS

0 if all pass; 1 otherwise. One test that exercises the installer's platform
refusal is skipped on Linux.

---

## demo-service/cedar-demo

### NAME

`cedar-demo` - the harmless service program

### SYNOPSIS

Run by systemd as `/opt/cedar-demo/cedar-demo` (unit
`demo-service/cedar-demo.service`).

### DESCRIPTION

Writes to standard output, which systemd sends to the journal (identifier
`cedar-demo`):

```text
cedar-demo startup startup_id=<12 hex> pid=<pid> uid=<uid>
cedar-demo heartbeat startup_id=<12 hex> seq=<n>        every 15 seconds
cedar-demo shutdown startup_id=<12 hex> reason=SIGTERM
```

The `startup_id` is new for each run, so it distinguishes one instance from the
next, alongside systemd's `InvocationID`. It handles `SIGTERM` and `SIGINT` by
logging the shutdown line and exiting 0. It opens no sockets, reads no input and
writes no files. The unit runs it as the `cedar-demo` account with
`PrivateNetwork`, `NoNewPrivileges`, `ProtectSystem=strict` and a system-call
filter; each setting is commented in the unit file.

### EXIT STATUS

0 on a clean shutdown.
