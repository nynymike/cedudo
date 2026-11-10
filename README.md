# Overview

`cedudo` is a more restrictive alternative to the `sudo` command where Cedar policies
are used to control access to what linux commands a user can run. Cedudo looks up
the Linux groups of the user and maps other information into the context, e.g. time of 
day. Cedudo is very restrictive by design, and is meant for demo purposes.

## Guides

- [`workshop-overview.md`](workshop-overview.md): the 80-minute student workshop and the restart exercise.
- [`docs/demo-service.md`](docs/demo-service.md): administering the `cedar-demo` service (install, validate, business-hours testing, uninstall).
- [`docs/cedudo.md`](docs/cedudo.md): how `cedudo` works, the authorization request, and writing policies.
- [`docs/tools.md`](docs/tools.md): manual-page style reference for every command, script and program in this repository.
- [`docs/oidc-login.md`](docs/oidc-login.md): optional OIDC login with authd.

Sections below: supported environment, administrator prerequisites, install,
verify, test as students, troubleshooting, update and redeploy, uninstall.

# Installing cedudo

This document describes how to install `cedudo` as a setuid-root executable.

## 1. Supported environment

**Supported workshop environment: Ubuntu 24.04 LTS with systemd running, using
its system Python 3 (3.12).** The complete workshop installation (Cedudo plus
the `cedar-demo` service) is supported and tested only there.

| Component | Requirement |
| --- | --- |
| Complete workshop (Cedudo + `cedar-demo.service`, exercises) | Ubuntu 24.04 with systemd running, system Python. `tools/install-demo-service.sh` refuses to run anywhere else. |
| `cedudo.py` alone | Linux with a compiler, Python 3.9 or later (it imports `zoneinfo`, which Python 3.8 lacks) and a `cedarling-python` build for your platform. Not tested outside Ubuntu 24.04. |
| Architecture | The pinned `cedarling-python` publishes Linux **x86_64** wheels only (CPython 3.10 to 3.12). An ARM (aarch64) VM has no wheel and will not work. |
| `tools/cedudo-simulate.py`, `tests/` | Python 3.9 or later, any OS. No root or systemd. |

An ordinary container (for example a default Docker image) does **not** meet
the installer's requirements: it normally has no systemd running, so the
`cedar-demo` service cannot be installed, started, or restarted. Use an Ubuntu
24.04 VM.

## 2. Administrator prerequisites

- An ordinary administrator account with `sudo` rights (see "Administrator context" below)
- Git
- GCC (to compile the C wrapper)
- Python 3 with `venv` and `pip` (system Python on Ubuntu 24.04)
- `zip` and `unzip` (used by `tools/build-cjar.sh` and `tools/deploy-policy.sh`)
- `cedarling_python` (the Janssen Cedarling Python bindings), pinned in `requirements.txt`

Install the build and Python tools on Ubuntu 24.04:

```bash
sudo apt update
sudo apt install gcc python3 python3-venv python3-pip git zip unzip
```

### Administrator context

Every installation step is performed by an **ordinary administrator account
with `sudo` rights**, working in a clone in that account's home directory. Do
not open a root shell and do not clone into `/root`.

- Commands that change the system are written with an explicit `sudo`.
- `install-wrapper.sh` and `tools/deploy-policy.sh` are run **as yourself,
  without `sudo`**. They call `sudo` internally for the privileged parts, so
  the compiler runs as you and only the install steps run as root.
- `tools/install-demo-service.sh`, `tools/uninstall-demo-service.sh` and
  `tools/test-demo-service.sh` check that they are running as root, so run them
  **with** `sudo`.
- Students use their own accounts (`alice`, `bob`) and never run any of this.

## 3. Install

### 1. Clone the repository

As your administrator account:

```bash
cd ~
git clone https://github.com/nynymike/cedudo.git
cd ~/cedudo
```

Later steps assume you are in this clone.

Before going further, run the two pre-install checks (details under "Verify"):

```bash
./tools/install-demo-service.sh --check
python3 -m unittest discover -s tests
```

Fix anything reported before continuing.

### 2. Create the installation directory

```bash
sudo install -d -o root -g root -m 0755 /opt/cedudo
```



### 3. Set up the Python virtual environment and install `cedarling_python`

`cedudo.py` imports `cedarling_python`. Install that module into the
`/opt/cedudo/venv` interpreter the C wrapper uses. The PyPI package name is
`cedarling-python`; the import name is `cedarling_python`. The version is
pinned in [`requirements.txt`](requirements.txt) so every workshop VM gets the
same build.

```bash
sudo python3 -m venv /opt/cedudo/venv
sudo /opt/cedudo/venv/bin/python3 -m pip install -r requirements.txt
```

The venv is created by root so that it is root-owned, which is what the setuid
wrapper relies on.

Confirm the module is available (this must succeed before you continue):

```bash
/opt/cedudo/venv/bin/python3 -c "import cedarling_python; print('cedarling_python OK')"
```

If that command raises `ModuleNotFoundError: No module named 'cedarling_python'`,
the package is not installed in this venv. Re-run the `pip install -r requirements.txt` above and
do not run `cedudo.py` with system `python3`.

### 4. Package the policy store and copy the files

First package the policy store under `policy/store/` into the Cedar Archive.
As your administrator account (no `sudo`; it writes into your clone):

```bash
./tools/build-cjar.sh
```

This rebuilds `policy/cedudo.cjar` from the source policies, so the archive you
install matches what is in `policy/store/`. It is packaging, not validation:
the script checks that the required files exist, that `metadata.json` has the
required keys, and that each `.cedar` file has one `@id(...)`, then zips the
store. It does **not** parse the policies or check them against the schema. A
policy error shows up later, when Cedarling loads the archive. Rebuilding
changes the checked-in `policy/cedudo.cjar` (zip timestamps), which is expected.

Then install the files:

```bash
sudo install -o root -g root -m 0644 cedudo.py /opt/cedudo/cedudo.py
sudo install -o root -g root -m 0644 operations.json /opt/cedudo/operations.json
sudo install -o root -g root -m 0644 policy/cedudo.cjar /opt/cedudo/cedudo.cjar
```

`install` sets the owner, group and mode in the same step, so the files are
never left with the permissions of your clone. Do not use plain `cp` here.

**Everything cedudo trusts must stay under administrator control.** The
setuid wrapper runs as root, and it executes the interpreter, the Python
environment and the application code. Root then trusts the manifest and the
policy archive to decide and define what runs. Anyone who can modify any of
these can run arbitrary code as root or change what is authorized:

| Item | Required state |
| --- | --- |
| `/opt/cedudo/` and `/opt/cedudo/venv/` (and everything in them) | owned by `root:root`, not group- or world-writable |
| `/opt/cedudo/venv/bin/python3` and the system Python it points to (`/usr/bin/python3`) | owned and writable only by root |
| `/opt/cedudo/cedudo.py` | `root:root 0644` |
| `/opt/cedudo/operations.json` | `root:root 0644` |
| `/opt/cedudo/cedudo.cjar` | `root:root 0644` |
| `/opt/cedudo/cedudo` (setuid wrapper) | `root:root 4755`, set by `install-wrapper.sh` |
| `/opt` and `/usr/local/bin` (parents) | owned by root, not group- or world-writable |

Only `install-wrapper.sh` handles the wrapper and its symlink; it does not
secure the other files. At runtime `cedudo` also refuses a manifest or
archive that is not a root-owned regular file without group/world write
access, but it does not check `cedudo.py` or the Python environment, so
verify them yourself under "Verify" below.



### 5. Create C wrapper

**Important:** Most modern Linux systems don't allow setuid on interpreted scripts. You must use the compiled C wrapper:

```bash
# Run as your administrator account, WITHOUT sudo; the script uses sudo itself
chmod +x install-wrapper.sh
./install-wrapper.sh
```

This creates `/opt/cedudo/cedudo` (a compiled binary with setuid, `root:root 4755`) and the `/usr/local/bin/cedudo` symlink. It secures only the wrapper; the other files were secured in step 4. To recover a missing or wrong wrapper, rerun this script; do not assemble the wrapper by hand.


Verify ownership is root 
```bash
stat -c '%u' /opt/cedudo/cedudo
```
Should output `0`


```bash
stat -c '%a' /opt/cedudo/cedudo
```

Should output `4755`

### 6. Create the demo users

The starter policies authorize by Linux group. Create `alice` in `developers` and `bob` in `operators`, each with a home directory and bash as the login shell (`useradd` otherwise defaults to `/bin/sh`):

```bash
sudo groupadd developers
sudo groupadd operators
sudo useradd -m -s /bin/bash -G developers alice
sudo useradd -m -s /bin/bash -G operators bob
```


| User      | Groups       | Starter intent                                                    |
| --------- | ------------ | ----------------------------------------------------------------- |
| **alice** | `developers` | May observe the demo (`read-logs`); may **not** restart |
| **bob**   | `operators`  | May observe the demo and restart **noncritical** services when `intruder_risk_level` is `low` |


### 7. Install the demo service (administrator)

`read-logs` and `restart-demo` act on a real, harmless systemd service,
`cedar-demo.service`. Installing, validating, and removing it are administrator
tasks documented separately in [`docs/demo-service.md`](docs/demo-service.md).
In short, on the Ubuntu 24.04 VM:

```bash
sudo tools/install-demo-service.sh
```

Students never run this. (The installed manifest is the one from step 4; the
installer warns if it differs from the repository copy.)

Operations in `operations.json`:

| Operation | Cedar action / resource | Execution |
| --- | --- | --- |
| `read-logs` | `read-logs` on `Linux::Service::"cedar-demo"` | **Real**: `/usr/bin/journalctl --unit=cedar-demo.service --lines=20 --no-pager --output=short-iso` |
| `restart-demo` | `restart` on `Linux::Service::"cedar-demo"` | **Real**: `/usr/bin/systemctl --no-ask-password --no-pager restart cedar-demo.service` |
| `restart-ssh` | `restart` on `Linux::Service::"ssh"` (critical) | **Simulated**: prints a message; SSH is never restarted |

The caller supplies only the operation ID; extra arguments are logged and
ignored.

## 4. Verify

### Automated checks

Three automated checks are built in. Run each at the stage shown. The first two are also in step 1.

| Stage | Command | What it establishes |
| --- | --- | --- |
| Before installing (step 1) | `./tools/install-demo-service.sh --check` | Ubuntu 24.04, systemd running, `systemctl`, `journalctl`, `python3`, `useradd` and friends present. Changes nothing. |
| Source checks (step 1) | `python3 -m unittest discover -s tests` | Static consistency: manifest IDs and exact arguments, docs and help text agree, the demo program and unit file, mocked `cedudo` behavior. No root or systemd needed. |
| After installing (below) | `sudo ./tools/test-demo-service.sh` | Real service behavior and the installed Cedudo working together on this VM. |

Limits to know about:

- **The preflight is not a Cedudo installation check.** `--check` looks only at
  what the demo service needs. It does not verify the venv, `cedarling_python`,
  the setuid wrapper, file ownership, the deployed archive, or the users. Only
  the final integration run exercises installed Cedudo.
- **The source checks do not touch the VM.** They run against the repository
  files, with Cedarling and systemd mocked or skipped.
- **The integration script can succeed with skipped checks.** Outside the
  `America/Chicago` window of 09:00 to 16:59, `forbid-restart-outside-hours`
  applies, so the script skips the allowed-restart check (new `InvocationID` and
  startup journal entry) and verifies an after-hours denial instead. It still
  exits 0. Read its final `RESULT:` line: `PASSED (nothing skipped)` is the full
  result, `PASSED WITH SKIPS` means the allowed path is unverified. Add
  `--strict` to make skips fail. Changing the VM clock is not the routine fix;
  see "Business hours: three ways to test" below.

Verify file ownership and permissions across the whole installation. As your administrator account:

```bash
# Parent directories and key files: expect root:root and no group/world write
stat -c '%U:%G %a %n' /opt /opt/cedudo /opt/cedudo/cedudo.py \
    /opt/cedudo/operations.json /opt/cedudo/cedudo.cjar /opt/cedudo/cedudo \
    /usr/local/bin /usr/bin/python3

# Should print NOTHING: anything under /opt/cedudo (venv included) that is
# not root-owned or is group/world-writable. Symlinks are skipped; the venv
# python3 symlink target is checked above.
sudo find /opt/cedudo -not -type l \( ! -user root -o -perm /022 \) -print
```

If the `find` prints anything, fix it before continuing to the student tests, for example with
`sudo chown -R root:root /opt/cedudo` and `sudo chmod -R go-w /opt/cedudo`.

Then run the integration check as your administrator account. It needs root, the installed Cedudo, the deployed policy, and `alice` and `bob`:

```bash
sudo ./tools/test-demo-service.sh
```

Read the final `RESULT:` line. `PASSED WITH SKIPS` is not a full pass; see
"Business hours: three ways to test" below.

## 5. Test as students

### Business hours: three ways to test

The deployed `forbid-restart-outside-hours` policy denies every `restart`
request when the `America/Chicago` hour is before 09:00 or at or after 17:00,
on any day. It does not affect `read-logs`. `cedudo` reads the server clock;
callers cannot override it, and the policy is not weakened for testing.
**Do not change the VM clock as a routine workaround**, especially on a VM that
also uses OIDC login or certificate validation. Choose one:

| Choice | Use when | Proves |
| --- | --- | --- |
| 1. Test `read-logs` and the after-hours denial now | Any time | Install works; the forbid policy fires; a denied restart changes nothing |
| 2. Explore an allowed daytime decision with the simulator | Any time | The policy *would* allow bob at 10:00 (no execution) |
| 3. Run the real allowed-restart check in the window | 09:00 to 16:59 Central | A permitted restart really happens |

Simulator command (use the venv interpreter, because the script's
`#!/usr/bin/env python3` line would pick the system Python without
`cedarling_python`):

```bash
/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py restart-demo \
    --user bob --uid 1001 --gid 1001 --groups operators \
    --hour 10 --day-of-week 2 --is-weekend false \
    --policy-store /opt/cedudo/cedudo.cjar
```

Details, and a clearly fenced last-resort procedure for pinning the clock on an
isolated, disposable VM only, are in
[`docs/demo-service.md`](docs/demo-service.md). Outputs below that show a
permitted restart assume choice 3 (inside the window).

### Switching to student identities

Run these from your **administrator account**. `sudo -iu <user>` opens a login
shell as that user, and `exit` returns you to your administrator shell. The demo
accounts need **no password** for this: `useradd` leaves them with a locked
password, and `sudo` does not ask for the target user's password. Setting
passwords or SSH login for students is a separate, optional step (see "Optional: passwords or SSH login" below).

`cedudo explain <operation-id>` is a dry run. It shows your actual identity
(uid, gid, groups), the Cedar action and resource, every context value and its
source, the policy-store fingerprint, the decision with its determining policy
IDs, and the command that *would* run. It never executes the operation, so it is
a safe way to see a decision before (or instead of) causing it.

Copy each block as a whole.

### Test as alice

```bash
sudo -iu alice
id
cedudo read-logs
cedudo explain restart-demo
exit
```

Expected: `id` shows `alice` in `developers` and not in `operators`.
`read-logs` is permitted (`developers-observe-demo`) and prints up to 20 recent
`cedar-demo` journal entries. `explain restart-demo` reports `DENY` with no
determining policy: Cedar is default-deny and nothing permits alice to restart.

Audit lines on stderr look like this:

>cedudo[4669]: INFO PERMIT user=alice uid=1000 groups=['alice', 'developers'] operation=read-logs action=Linux::Action::"read-logs" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['developers-observe-demo'] exec=['/usr/bin/journalctl', '--unit=cedar-demo.service', '--lines=20', '--no-pager', '--output=short-iso']

To see an actual denial and the critical-resource protection, still as alice:

```bash
sudo -iu alice
cedudo restart-demo
cedudo restart-ssh
exit
```

>cedudo[4702]: WARNING DENY user=alice uid=1000 groups=['alice', 'developers'] operation=restart-demo action=Linux::Action::"restart" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=[]
>cedudo: denied: restart-demo

>cedudo[4708]: WARNING DENY user=alice uid=1000 groups=['alice', 'developers'] operation=restart-ssh action=Linux::Action::"restart" resource=Linux::Service::"ssh" local_console=False interactive=True intruder_risk_level=low policies=['forbid-critical-restart']

### Test as `bob`

```bash
sudo -iu bob
id
cedudo explain restart-demo
cedudo restart-demo
exit
```

Expected inside the business-hours window: `id` shows `bob` in `operators`.
`explain restart-demo` reports `ALLOW` with determining policy
`operators-restart`. `cedudo restart-demo` then really restarts
`cedar-demo.service`:

>cedudo[4729]: INFO PERMIT user=bob uid=1001 groups=['bob', 'operators'] operation=restart-demo action=Linux::Action::"restart" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['operators-restart'] exec=['/usr/bin/systemctl', '--no-ask-password', '--no-pager', 'restart', 'cedar-demo.service']

The restart itself prints nothing. Confirm it from any account: the
`InvocationID` changes.

```bash
systemctl show cedar-demo.service -p InvocationID -p ActiveState
```

Outside the window, `explain` shows `DENY` with `forbid-restart-outside-hours`,
and `restart-demo` is denied without touching the service.

Bob and the critical SSH resource (the execution is simulated either way):

```bash
sudo -iu bob
cedudo restart-ssh
exit
```

>cedudo[4735]: WARNING DENY user=bob uid=1001 groups=['bob', 'operators'] operation=restart-ssh action=Linux::Action::"restart" resource=Linux::Service::"ssh" local_console=False interactive=True intruder_risk_level=low policies=['forbid-critical-restart']
>cedudo: denied: restart-ssh

The `local_console` and `is_remote` values depend on how you reached the VM: an
administrator logged in over SSH is reported as remote, even through
`sudo -iu`. `explain` shows the value and where it came from.

### Optional: passwords or SSH login for students

Skip this if you drive all testing from the administrator account. It is needed
only when students must log in as `alice` or `bob` themselves (for example
`su - bob` between accounts, or SSH). It is not required for any step above.

```bash
sudo passwd alice
sudo passwd bob
```

SSH access depends on your VM's `sshd` configuration (password authentication
is often disabled by default on Ubuntu images) and is outside this guide. Use a
throwaway password you hand out for the workshop, and remove it afterwards with
`sudo passwd -l alice` and `sudo passwd -l bob`.

### Optional: OIDC login

Logging in through an OIDC identity provider (Ubuntu authd) is **optional** and
not needed for the local `alice` and `bob` exercises. A successful OIDC login
does not by itself authorize any Cedudo operation; the starter policies check
the Linux groups `developers` and `operators`. See
[`docs/oidc-login.md`](docs/oidc-login.md), including its "Groups and
authorization" section.

## 6. Troubleshooting

The installers are the single source of truth for how the wrapper, the demo
service and the policy archive are installed, so recovery means rerunning them,
not following a second recipe. After any fix, repeat "Verify".

| Symptom | Cause and fix |
| --- | --- |
| `ERROR direct root invocation is not a workshop principal` | Deliberate. `cedudo` authorizes the *original* Linux user, so it refuses to run as root (including `sudo cedudo` and a root shell). Run it as a student: `sudo -iu alice`, then `cedudo …`, then `exit`. |
| `cedudo: command not found`, or `Permission denied` for a regular user | The symlink or wrapper is missing or not executable. Rerun `./install-wrapper.sh` (administrator account, no `sudo`), then check `stat -c '%U:%G %a' /opt/cedudo/cedudo` shows `root:root 4755` and `ls -l /usr/local/bin/cedudo` points to `/opt/cedudo/cedudo`. |
| `must be installed as setuid root` | `cedudo` ran without the setuid bit: the Python script was run directly, or the wrapper's mode or owner is wrong. Rerun `./install-wrapper.sh`; do not run `cedudo.py` yourself. |
| `ModuleNotFoundError: No module named 'cedarling_python'` | The wrapper's venv lacks the package. From the clone: `sudo /opt/cedudo/venv/bin/python3 -m pip install -r requirements.txt`. Do not use the system `python3`. |
| `cannot inspect policy store` / `policy store must be owned by root` | The archive is missing or not a root-owned regular file. Redo the file-copy commands in step 4, then the ownership check under "Verify". |
| `Cedarling initialization failed` | The archive is missing, invalid, or the `cedarling-python` build does not match it. Rebuild with `./tools/build-cjar.sh` and redeploy (see "Update and redeploy"); confirm `metadata.json` uses `cedar_version`. |
| `unknown operation: X` | `X` is not in `/opt/cedudo/operations.json`. `root-shell` is deliberately absent. Check the installed manifest matches the repository copy. |
| `invoking user not found` / `identity does not match the local account database` | The calling uid is not in the account database. Use a real local account. |
| `restart-demo` denied during the day | Check `cedudo explain restart-demo` as that user: groups and determining policy IDs. `alice` is denied by default; `bob` needs `operators`. |
| `restart-demo` denied for `bob` and the hour looks wrong | `forbid-restart-outside-hours` uses `America/Chicago` time. See "Business hours: three ways to test"; do not change the clock casually. |
| `PERMIT` but nothing changed | Authorization succeeded; the command failed or did nothing. Compare `systemctl show cedar-demo.service -p InvocationID` before and after, and run `systemctl status cedar-demo`. |
| `cedar-demo.service` missing or inactive | Rerun `sudo tools/install-demo-service.sh` and see `docs/demo-service.md`. |
| `RESULT: PASSED WITH SKIPS` | Not a failure, but the allowed restart was not verified. See "Business hours: three ways to test". |

## 7. Update and redeploy

Change one thing at a time, redeploy it with the same commands as the install,
then repeat "Verify". Run scripts as your administrator account; they call
`sudo` where needed.

| What changed | Redeploy |
| --- | --- |
| Cedar policies or schema in `policy/store/` | `./tools/build-cjar.sh` then `./tools/deploy-policy.sh` |
| `cedudo.py` | `sudo install -o root -g root -m 0644 cedudo.py /opt/cedudo/cedudo.py` |
| `operations.json` | `sudo install -o root -g root -m 0644 operations.json /opt/cedudo/operations.json`, then `sudo tools/install-demo-service.sh` (warns if the installed manifest differs) |
| The C wrapper | `./install-wrapper.sh` |
| `demo-service/` program or unit | `sudo tools/install-demo-service.sh` (restarts the service only if the files changed) |
| The `cedarling-python` pin | Edit `requirements.txt`, then `sudo /opt/cedudo/venv/bin/python3 -m pip install -r requirements.txt` and retest the whole workshop |

After a policy redeploy, check the effect as a student with
`cedudo explain <operation-id>` before relying on it.

## 8. Uninstall

Each step is separate; stop wherever you want to keep something.

**1. The demo service** (stops and disables it; removes only the unit,
`/opt/cedar-demo`, and the `cedar-demo` account if the installer created it; it
does not touch `/opt/cedudo`, `alice`, `bob` or the shared groups):

```bash
sudo tools/uninstall-demo-service.sh
```

**2. Cedudo itself:**

```bash
sudo rm -rf /opt/cedudo
# Remove the symlink only if it points at the wrapper you installed:
[ "$(readlink /usr/local/bin/cedudo)" = /opt/cedudo/cedudo ] && sudo rm /usr/local/bin/cedudo
```

**3. Optional: the demo users and groups.** Do this only if you created
`alice`, `bob`, `developers` and `operators` just for this workshop. Other
software or people may use those groups.

```bash
sudo userdel -r alice
sudo userdel -r bob
sudo groupdel developers
sudo groupdel operators
```

**4. Optional: your source clone.** Uninstalling the application does not
remove the repository you cloned, and its location is wherever you chose. Delete
it yourself if you no longer need it.
