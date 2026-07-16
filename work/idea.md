# Workshop Outline: Build a Safer `sudo` with Cedar

## Core concept

Do **not** attempt to replace `sudo` itself during the workshop. Instead:

1. `sudo` performs the Unix privilege transition.
2. A root-owned helper named `cedudo` acts as the **Policy Enforcement Point**.
3. Cedarling acts as the local **Policy Decision Point**.
4. Tarp acts as the browser-based policy workbench.
5. Both Tarp and `cedudo` evaluate the **same `.cjar` policy store**.

Tarp includes Cedarling as WASM and supports unsigned authorization requests, making it suitable for testing principal, action, resource and context inputs without first deploying an identity provider. Tarp loads the policy store from a URL, while the Python Cedarling binding can load the same `.cjar` from a local file. ([docs.jans.io][1])

```text
                    Same cedudo.cjar
                     /             \
                    v               v

Browser + Tarp                  Local VM
Cedarling WASM                  sudo cedudo restart-demo
Policy testing                         |
                                       v
                               Cedarling Python
                                       |
                               Permit or Deny
                                       |
                              Fixed root command
```

The key lesson is:

> Cedar decides whether a privileged capability is allowed. The enforcement wrapper determines exactly which executable and arguments that capability represents.

---

## Attendee outcome

By the end, attendees should be able to:

* Model a Linux privilege as a Cedar principal–action–resource request.
* Test permit and deny decisions with Tarp.
* Modify a Cedar policy and reload the policy store.
* Run a local Cedarling decision from a privileged helper.
* Permit a safe administrative operation.
* Deny a root shell and unauthorized service operation.
* Understand the separation between policy decision, enforcement and privilege escalation.

---

# Local VM Design

Use a prepared Ubuntu or Debian VM. Avoid spending workshop time installing dependencies or building Tarp.

Tarp can be installed from its prebuilt Chrome or Firefox release package; building it from source currently involves Node.js and an npm build process, which is unnecessary workshop overhead. ([GitHub][2])

## VM users

Create two demonstration users:

| User    | Linux groups | Intended permissions                   |
| ------- | ------------ | -------------------------------------- |
| `alice` | `developers` | Read logs, but not restart services    |
| `bob`   | `operators`  | Read logs and restart the demo service |

The attendee initially logs in as `alice`.

## Harmless demonstration service

Install a simple systemd service:

```text
cedar-demo.service
```

It could run a tiny HTTP server or shell loop. The service should:

* Write a timestamp to its journal.
* Be safe to restart repeatedly.
* Have no network dependency.
* Contain no important data.

Example operations:

| Operation ID   | Cedar action | Cedar resource          | Executed command                 |
| -------------- | ------------ | ----------------------- | -------------------------------- |
| `status-demo`  | `ViewStatus` | `Service::"cedar-demo"` | `systemctl status cedar-demo`    |
| `view-logs`    | `ReadLogs`   | `Service::"cedar-demo"` | `journalctl -u cedar-demo -n 20` |
| `restart-demo` | `Restart`    | `Service::"cedar-demo"` | `systemctl restart cedar-demo`   |
| `root-shell`   | `OpenShell`  | `Host::"workshop-vm"`   | Deliberately denied              |

The helper must accept only these operation IDs. It must **not** accept arbitrary executable names or shell command strings.

---

# Files Supplied in the VM

```text
~/cedudo-workshop/
├── policy/
│   ├── cedar-policy.cedar
│   ├── cedar-schema.json
│   └── cedudo.cjar
├── examples/
│   ├── alice-read-logs.json
│   ├── alice-restart.json
│   └── bob-restart.json
├── tools/
│   ├── build-cjar.sh
│   ├── serve-policy.py
│   └── deploy-policy.sh
└── README.md

/opt/cedudo/
├── cedudo.cjar
├── operations.json
├── cedudo.py
└── venv/

/usr/local/sbin/cedudo
/etc/sudoers.d/cedudo
```

## Local policy server

Tarp requires the `.cjar` to be accessible through a URL. The workshop VM can run a tiny local HTTP server with CORS enabled:

```bash
cd ~/cedudo-workshop/policy
python3 ../tools/serve-policy.py
```

Tarp then uses:

```text
http://127.0.0.1:8000/cedudo.cjar
```

Current Cedarling documentation specifies loading a `.cjar` through a URI when Cedarling runs in Tarp’s WASM environment. ([docs.jans.io][1])

---

# Authorization Model

## Principal

The principal represents the original Linux user—not root, even though the helper runs through `sudo`.

```json
{
  "cedar_entity_mapping": {
    "entity_type": "Linux::User",
    "id": "alice"
  },
  "uid": 1000,
  "groups": ["developers"]
}
```

The wrapper obtains this information from the operating system using values such as:

* `SUDO_USER`
* `SUDO_UID`
* The system user and group databases

It must not accept the username or group list from command-line arguments.

## Action

Examples:

```text
Linux::Action::"ViewStatus"
Linux::Action::"ReadLogs"
Linux::Action::"Restart"
Linux::Action::"OpenShell"
```

## Resource

For the service:

```json
{
  "cedar_entity_mapping": {
    "entity_type": "Linux::Service",
    "id": "cedar-demo"
  },
  "environment": "workshop",
  "critical": false
}
```

For a root shell attempt:

```json
{
  "cedar_entity_mapping": {
    "entity_type": "Linux::Host",
    "id": "workshop-vm"
  }
}
```

## Context

```json
{
  "local_console": true,
  "interactive": true
}
```

The wrapper derives this context. For example, it could set `local_console` to false when `SSH_CONNECTION` is present.

Cedar treats principal, action and resource as the stable elements of the authorization request, while context is intended for point-in-time request information. ([Cedar Policy Language Reference Guide][3])

---

# Starting Cedar Policies

## Developers can read logs

```cedar
permit (
    principal,
    action == Linux::Action::"ReadLogs",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal.groups.contains("developers") ||
    principal.groups.contains("operators")
};
```

## Operators can restart locally

```cedar
permit (
    principal,
    action == Linux::Action::"Restart",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal.groups.contains("operators") &&
    context.local_console
};
```

## Explicitly block root shells

```cedar
forbid (
    principal,
    action == Linux::Action::"OpenShell",
    resource
);
```

Cedar is default-deny: a request is denied unless a matching `permit` policy authorizes it. A matching `forbid` overrides any matching permit, which makes the root-shell policy useful for demonstrating an invariant. ([Cedar Policy Language Reference Guide][4])

---

# The `cedudo` Enforcement Helper

Attendees do not need to write the whole helper. Provide most of it and leave one or two clearly marked sections for them to complete.

## Invocation

```bash
sudo cedudo view-logs
sudo cedudo restart-demo
sudo cedudo root-shell
```

## Operation manifest

```json
{
  "view-logs": {
    "action": "Linux::Action::\"ReadLogs\"",
    "resource_type": "Linux::Service",
    "resource_id": "cedar-demo",
    "argv": [
      "/usr/bin/journalctl",
      "-u",
      "cedar-demo",
      "-n",
      "20",
      "--no-pager"
    ]
  },
  "restart-demo": {
    "action": "Linux::Action::\"Restart\"",
    "resource_type": "Linux::Service",
    "resource_id": "cedar-demo",
    "argv": [
      "/usr/bin/systemctl",
      "restart",
      "cedar-demo"
    ]
  }
}
```

Do not put `root-shell` in the executable manifest. Attendees can test its authorization request in Tarp, but the VM helper should have no corresponding executable operation.

## Enforcement sequence

```text
1. Validate operation ID.
2. Look it up in a root-owned operation manifest.
3. Determine the original user from sudo.
4. Read the user's real Linux groups.
5. Construct the Cedar principal.
6. Construct the action and resource.
7. Derive trusted request context.
8. Call Cedarling authorize_unsigned.
9. If denied, log and exit.
10. If permitted, execve the fixed argv array.
```

Cedarling’s Python interface supports unsigned authorization by passing an application-constructed principal, action, resource and context. It also fails closed when authorization cannot be fully determined. ([docs.jans.io][5])

## Essential implementation rule

Never do this:

```python
subprocess.run(user_supplied_command, shell=True)
```

Use a fixed argument array:

```python
os.execv(operation["argv"][0], operation["argv"])
```

The authorization decision applies to the named capability, and the root-owned manifest binds that capability to one exact executable operation.

---

# 80-Minute Agenda

## 0–8 minutes — Why `sudoers` becomes difficult

Demonstrate ordinary sudo configuration:

```text
alice may run this command
bob may run that command
only on this machine
perhaps only with these arguments
```

Introduce the workshop architecture:

* `sudo`: privilege transition.
* `cedudo`: enforcement point.
* Cedarling: decision point.
* Tarp: testing and inspection client.
* `.cjar`: shared policy artifact.

## 8–18 minutes — Inspect the VM

Attendees run:

```bash
id
systemctl status cedar-demo
sudo cedudo view-logs
sudo cedudo restart-demo
```

Initial expected result:

```text
alice -> view-logs: PERMIT
alice -> restart-demo: DENY
```

Show that direct access is unavailable:

```bash
sudo systemctl restart cedar-demo
```

The sudoers configuration should permit only the `cedudo` helper, not the underlying administrative commands.

## 18–32 minutes — Reproduce the decision in Tarp

Configure Tarp with the locally served `.cjar`.

Use the unsigned authorization form. Tarp’s unsigned mode allows the application—or, here, the attendee—to supply the principal directly without JWT validation. ([docs.jans.io][1])

Test:

1. Alice reads logs: permit.
2. Alice restarts service: deny.
3. Bob restarts service locally: permit.
4. Bob restarts over SSH context: deny.
5. Bob requests a root shell: deny.

This teaches PARC without introducing OAuth.

## 32–45 minutes — Read and modify the policies

Attendees inspect the three policies.

Challenge:

> Permit members of `developers` to restart the demo service, but only when the resource is noncritical and the request originates from the local console.

Possible policy:

```cedar
permit (
    principal,
    action == Linux::Action::"Restart",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal.groups.contains("developers") &&
    !resource.critical &&
    context.local_console
};
```

Rebuild the archive:

```bash
./tools/build-cjar.sh
```

Reload Cedarling in Tarp and rerun the request.

## 45–58 minutes — Deploy the same policy to the VM helper

Deploy the rebuilt policy:

```bash
sudo ./tools/deploy-policy.sh
```

The script should:

* Validate the archive.
* Copy it into `/opt/cedudo/cedudo.cjar`.
* Set root ownership.
* Set nonwritable permissions.

Run:

```bash
sudo cedudo restart-demo
```

Alice should now receive a permit, and the service should restart.

This is the workshop’s central moment: the same policy tested in the browser now controls a real local administrative operation.

## 58–70 minutes — Attack the design

Give attendees several attempts:

```bash
sudo cedudo ../../bin/bash
sudo cedudo "restart-demo; /bin/bash"
sudo cedudo restart-demo --service ssh
sudo cedudo root-shell
```

All must fail.

Discuss why:

* The helper recognizes operation IDs, not commands.
* No `shell=True`.
* Arguments come from a root-owned manifest.
* Identity and groups come from the OS.
* Policies are root-owned.
* Unknown operations fail closed.
* A permit does not allow the caller to change the executable arguments.

## 70–77 minutes — Add one contextual control

Attendees choose one:

* Deny restart from an SSH session.
* Deny operations against a critical service.
* Require membership in both `operators` and `oncall`.
* Permit log viewing but deny log deletion.
* Permit restart only when a change-ticket field is present.

Example invariant:

```cedar
forbid (
    principal,
    action == Linux::Action::"Restart",
    resource
)
when {
    !context.local_console
};
```

## 77–80 minutes — Debrief

Summarize:

```text
Linux identity        -> Principal
Privileged capability -> Action
Service/file/host     -> Resource
Session conditions    -> Context
Cedarling             -> Decision
cedudo                 -> Enforcement
sudo                   -> Privilege transition
```

---

# What Should Be Prepared Before the Workshop

To reliably fit in 80 minutes, provide:

* A downloadable VM image.
* Tarp already installed.
* The Cedarling Python dependency already installed.
* The demo service already running.
* The sudoers entry already configured.
* A working starter `.cjar`.
* A local policy web server.
* Copy-and-paste Tarp request examples.
* A reset script:

```bash
sudo /opt/cedudo/reset-workshop
```

Do not make attendees:

* Install Janssen Server.
* Configure an OIDC provider.
* Build Tarp from source.
* Debug browser extension permissions.
* Author a complete Cedar schema.
* Modify sudoers manually.
* Compile a privileged binary.

---

# Important Positioning

The title can remain **“Build a Safer `sudo` with Cedar,”** but the description should make clear that this is an educational integration, not a production-ready sudo replacement.

A production implementation would require:

* A small compiled, root-owned enforcement binary.
* Signed and versioned policy stores.
* Policy rollback protection.
* Secure decision logging.
* Stronger session authentication.
* Careful environment sanitization.
* Protection against policy and dependency tampering.
* Formal review of every operation-to-`argv` binding.
* Possibly JWT or workload-token authorization rather than application-asserted identity.

For the 80-minute version, the right scope is:

> Use Tarp to author and test Cedar authorization rules, then enforce those rules through a constrained local privilege wrapper on a Linux VM.

[1]: https://docs.jans.io/nightly/cedarling/quick-start/cedarling-quick-start/ "Quick Start - Janssen Documentation"
[2]: https://github.com/JanssenProject/jans/blob/main/demos/janssen-tarp/README.md "jans/demos/janssen-tarp/README.md at main · JanssenProject/jans · GitHub"
[3]: https://docs.cedarpolicy.com/policies/syntax-policy.html?utm_source=chatgpt.com "Basic Cedar syntax | Cedar Policy Language Reference Guide"
[4]: https://docs.cedarpolicy.com/auth/authorization.html?utm_source=chatgpt.com "Authorization | Cedar Policy Language Reference Guide"
[5]: https://docs.jans.io/head/cedarling/tutorials/python/ "Python - Janssen Documentation"


The complete workshop-ready script uses Cedarling’s current Python API: a local `.cjar` configured with `CEDARLING_POLICY_STORE_LOCAL_FN`, an unsigned `RequestUnsigned`, and `AuthorizeResult.is_allowed()`. ([docs.jans.io][1])([Jans Docs][1]):/mnt/data/cedudo.py)

It has been syntax-checked with `py_compile`. The implementation:

* Accepts only one operation ID—not a command or arguments.
* Derives the principal from `SUDO_USER`, `SUDO_UID`, local groups, and `/etc/passwd`.
* Loads commands from a root-owned `operations.json`.
* Loads `/opt/cedudo/cedudo.cjar`.
* Builds the Cedar principal, action, resource, and context.
* Fails closed on initialization, schema, or evaluation errors.
* Executes a fixed argument array with `os.execve()`.
* Uses a minimal environment and changes to `/` before execution.
* Logs permit and deny decisions to stderr and syslog.

## Companion `operations.json`

```json
{
  "view-logs": {
    "action": "Linux::Action::\"ReadLogs\"",
    "resource_type": "Linux::Service",
    "resource_id": "cedar-demo",
    "resource_attributes": {
      "environment": "workshop",
      "critical": false
    },
    "argv": [
      "/usr/bin/journalctl",
      "-u",
      "cedar-demo",
      "-n",
      "20",
      "--no-pager"
    ]
  },
  "status-demo": {
    "action": "Linux::Action::\"ViewStatus\"",
    "resource_type": "Linux::Service",
    "resource_id": "cedar-demo",
    "resource_attributes": {
      "environment": "workshop",
      "critical": false
    },
    "argv": [
      "/usr/bin/systemctl",
      "status",
      "cedar-demo",
      "--no-pager"
    ]
  },
  "restart-demo": {
    "action": "Linux::Action::\"Restart\"",
    "resource_type": "Linux::Service",
    "resource_id": "cedar-demo",
    "resource_attributes": {
      "environment": "workshop",
      "critical": false
    },
    "argv": [
      "/usr/bin/systemctl",
      "restart",
      "cedar-demo"
    ]
  }
}
```

## Installation

```bash
sudo mkdir -p /opt/cedudo

sudo cp cedudo.py /opt/cedudo/cedudo.py
sudo cp operations.json /opt/cedudo/operations.json
sudo cp cedudo.cjar /opt/cedudo/cedudo.cjar

sudo chown root:root \
    /opt/cedudo/cedudo.py \
    /opt/cedudo/operations.json \
    /opt/cedudo/cedudo.cjar

sudo chmod 0755 /opt/cedudo/cedudo.py
sudo chmod 0644 /opt/cedudo/operations.json
sudo chmod 0644 /opt/cedudo/cedudo.cjar

sudo ln -s /opt/cedudo/cedudo.py /usr/local/sbin/cedudo
```

The shebang expects Cedarling in:

```text
/opt/cedudo/venv/bin/python3
```

Create that environment with:

```bash
sudo python3 -m venv /opt/cedudo/venv
sudo /opt/cedudo/venv/bin/pip install cedarling-python
```

The Cedarling Python package is published through PyPI. ([Jans Docs][1])rs entry

Use `visudo` to create `/etc/sudoers.d/cedudo`:

```sudoers
%developers ALL=(root) /usr/local/sbin/cedudo *
%operators  ALL=(root) /usr/local/sbin/cedudo *
```

The wildcard is safe only because `cedudo.py` validates that the single argument is a known operation ID and never passes user-supplied arguments to the privileged executable.

Example:

```bash
sudo cedudo view-logs
sudo cedudo restart-demo
sudo cedudo root-shell
```

The last command is rejected before Cedar evaluation because `root-shell` has no root-owned manifest entry. For the workshop, participants can separately test the prohibited `OpenShell` action in Tarp.

[1]: https://docs.jans.io/head/cedarling/tutorials/python/ "Python - Janssen Documentation"


You’re right—the previous response linked the file but did not display its contents.

[Download `cedudo.py`](sandbox:/mnt/data/cedudo.py)

```python
#!/opt/cedudo/venv/bin/python3
"""Workshop Cedar-authorized privilege wrapper.

Usage:
    sudo /usr/local/sbin/cedudo view-logs
    sudo /usr/local/sbin/cedudo restart-demo

The caller supplies only an operation ID. The command and every argument come
from a root-owned manifest. Any Cedarling/configuration error fails closed.
"""

from __future__ import annotations

import argparse
import grp
import json
import logging
import logging.handlers
import os
import pwd
import re
import socket
import stat
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

from cedarling_python import (
    BootstrapConfig,
    CedarEntityMapping,
    Cedarling,
    EntityData,
    RequestUnsigned,
)

APP = "cedudo"
POLICY_STORE = Path("/opt/cedudo/cedudo.cjar")
OPERATIONS_FILE = Path("/opt/cedudo/operations.json")
OPERATION_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")

EX_USAGE = getattr(os, "EX_USAGE", 64)
EX_CONFIG = getattr(os, "EX_CONFIG", 78)
EX_NOPERM = getattr(os, "EX_NOPERM", 77)
EX_UNAVAILABLE = getattr(os, "EX_UNAVAILABLE", 69)
EX_SOFTWARE = getattr(os, "EX_SOFTWARE", 70)


def make_logger() -> logging.Logger:
    logger = logging.getLogger(APP)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(name)s[%(process)d]: %(levelname)s %(message)s"
    )

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(formatter)
    logger.addHandler(stderr)

    if Path("/dev/log").exists():
        try:
            syslog = logging.handlers.SysLogHandler(address="/dev/log")
            syslog.setFormatter(formatter)
            logger.addHandler(syslog)
        except OSError:
            pass

    return logger


LOG = make_logger()


def fail(message: str, code: int = EX_NOPERM) -> NoReturn:
    """Log an error and terminate without executing anything."""
    LOG.error(message)
    raise SystemExit(code)


def require_trusted_file(path: Path, label: str) -> None:
    """Require a root-owned regular file that is not group/world writable."""
    try:
        info = path.lstat()
    except OSError as exc:
        fail(f"cannot inspect {label} {path}: {exc}", EX_CONFIG)

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        fail(
            f"{label} must be a regular, non-symlink file: {path}",
            EX_CONFIG,
        )

    if info.st_uid != 0:
        fail(f"{label} must be owned by root: {path}", EX_CONFIG)

    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        fail(
            f"{label} must not be group/world writable: {path}",
            EX_CONFIG,
        )


def invoking_user() -> tuple[pwd.struct_passwd, list[str]]:
    """Resolve the original user from sudo-controlled environment variables."""
    if os.geteuid() != 0:
        fail("must be invoked through sudo")

    name = os.environ.get("SUDO_USER")
    uid_text = os.environ.get("SUDO_UID")
    gid_text = os.environ.get("SUDO_GID")

    if not name or not uid_text or not gid_text:
        fail("missing SUDO_USER, SUDO_UID, or SUDO_GID")

    try:
        uid = int(uid_text)
        gid = int(gid_text)
        account = pwd.getpwnam(name)
    except (ValueError, KeyError):
        fail("invalid sudo identity")

    if uid == 0 or name == "root":
        fail("direct root invocation is not a workshop principal")

    if account.pw_uid != uid or account.pw_gid != gid:
        fail("sudo identity does not match the local account database")

    try:
        group_ids = os.getgrouplist(account.pw_name, account.pw_gid)
        groups = sorted(
            {
                grp.getgrgid(group_id).gr_name
                for group_id in group_ids
            }
        )
    except (KeyError, OSError) as exc:
        fail(f"cannot resolve local groups: {exc}", EX_UNAVAILABLE)

    return account, groups


def load_operation(operation_id: str) -> dict[str, Any]:
    """Load and validate one fixed privileged operation."""
    require_trusted_file(OPERATIONS_FILE, "operations manifest")

    try:
        manifest = json.loads(
            OPERATIONS_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot load operations manifest: {exc}", EX_CONFIG)

    if not isinstance(manifest, dict) or operation_id not in manifest:
        fail(f"unknown operation: {operation_id}")

    operation = manifest[operation_id]
    required = {
        "action",
        "resource_type",
        "resource_id",
        "argv",
    }

    if not isinstance(operation, dict) or not required.issubset(operation):
        fail(
            f"invalid manifest entry for {operation_id}",
            EX_CONFIG,
        )

    action = operation["action"]
    resource_type = operation["resource_type"]
    resource_id = operation["resource_id"]
    argv = operation["argv"]

    if not isinstance(action, str) or not action:
        fail(f"invalid action for {operation_id}", EX_CONFIG)

    if not isinstance(resource_type, str) or not resource_type:
        fail(f"invalid resource_type for {operation_id}", EX_CONFIG)

    if not isinstance(resource_id, str) or not resource_id:
        fail(f"invalid resource_id for {operation_id}", EX_CONFIG)

    if (
        not isinstance(argv, list)
        or not argv
        or not all(
            isinstance(value, str) and "\0" not in value
            for value in argv
        )
        or not os.path.isabs(argv[0])
    ):
        fail(f"invalid argv for {operation_id}", EX_CONFIG)

    # Resolve the executable now, then execute this exact path later.
    try:
        executable = Path(argv[0]).resolve(strict=True)
        info = executable.stat()
    except OSError as exc:
        fail(
            f"cannot inspect operation executable: {exc}",
            EX_CONFIG,
        )

    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
        fail(f"untrusted executable: {executable}", EX_CONFIG)

    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        fail(
            f"executable is group/world writable: {executable}",
            EX_CONFIG,
        )

    if not os.access(executable, os.X_OK):
        fail(
            f"executable is not executable: {executable}",
            EX_CONFIG,
        )

    operation["argv"] = [str(executable), *argv[1:]]
    operation.setdefault("resource_attributes", {})

    if not isinstance(operation["resource_attributes"], dict):
        fail(
            "resource_attributes must be a JSON object",
            EX_CONFIG,
        )

    return operation


def ancestor_names(pid: int) -> list[str]:
    """Return Linux process ancestor names on a best-effort basis."""
    names: list[str] = []
    seen: set[int] = set()

    while pid > 1 and pid not in seen:
        seen.add(pid)
        proc = Path("/proc") / str(pid)

        try:
            names.append(
                (proc / "comm").read_text(encoding="utf-8").strip()
            )

            status = (proc / "status").read_text(encoding="utf-8")
            parent_line = next(
                line
                for line in status.splitlines()
                if line.startswith("PPid:")
            )
            pid = int(parent_line.split(":", 1)[1].strip())
        except (OSError, StopIteration, ValueError):
            break

    return names


def build_context() -> dict[str, Any]:
    """Build authorization context from the execution environment."""
    remote = bool(
        os.environ.get("SSH_CONNECTION")
        or os.environ.get("SSH_CLIENT")
        or "sshd" in ancestor_names(os.getppid())
    )

    return {
        "current_time": int(time.time()),
        "hostname": socket.gethostname(),
        "local_console": not remote,
        "interactive": os.isatty(0) and os.isatty(1),
    }


def initialize_cedarling() -> Cedarling:
    """Initialize Cedarling using only the trusted local policy store."""
    require_trusted_file(POLICY_STORE, "policy store")

    # Prevent sudo-preserved variables from choosing another Cedarling
    # configuration or policy source.
    for name in tuple(os.environ):
        if name.startswith("CEDARLING_"):
            del os.environ[name]

    os.environ["CEDARLING_POLICY_STORE_LOCAL_FN"] = str(POLICY_STORE)
    os.environ["CEDARLING_APPLICATION_NAME"] = APP

    try:
        config = BootstrapConfig.from_env()
        return Cedarling(config)
    except Exception as exc:
        fail(
            f"Cedarling initialization failed: {exc}",
            EX_UNAVAILABLE,
        )


def authorize(
    cedarling: Cedarling,
    account: pwd.struct_passwd,
    groups: list[str],
    operation: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """Evaluate the unsigned Cedar authorization request."""
    principal = EntityData(
        cedar_entity_mapping=CedarEntityMapping(
            entity_type="Linux::User",
            id=account.pw_name,
        ),
        uid=account.pw_uid,
        gid=account.pw_gid,
        groups=groups,
        home=account.pw_dir,
        shell=account.pw_shell,
    )

    resource = EntityData(
        cedar_entity_mapping=CedarEntityMapping(
            entity_type=operation["resource_type"],
            id=operation["resource_id"],
        ),
        **operation["resource_attributes"],
    )

    request = RequestUnsigned(
        principal=principal,
        action=operation["action"],
        resource=resource,
        context=context,
    )

    try:
        result = cedarling.authorize_unsigned(request)
        return bool(result.is_allowed())
    except Exception as exc:
        fail(
            f"authorization evaluation failed: {exc}",
            EX_UNAVAILABLE,
        )


def safe_environment() -> dict[str, str]:
    """Return a minimal environment for the privileged child process."""
    return {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "USER": "root",
        "LOGNAME": "root",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TERM": "dumb",
        "PAGER": "cat",
        "SYSTEMD_PAGER": "cat",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a fixed privileged operation after Cedar authorization."
        )
    )

    parser.add_argument(
        "operation",
        help="operation ID from operations.json",
    )

    args = parser.parse_args()

    if not OPERATION_RE.fullmatch(args.operation):
        parser.error(
            "operation must match [a-z][a-z0-9-]{0,63}"
        )

    return args


def main() -> NoReturn:
    args = parse_args()

    account, groups = invoking_user()
    operation = load_operation(args.operation)
    context = build_context()

    cedarling = initialize_cedarling()
    allowed = authorize(
        cedarling,
        account,
        groups,
        operation,
        context,
    )

    audit = (
        f"user={account.pw_name} "
        f"uid={account.pw_uid} "
        f"operation={args.operation} "
        f"action={operation['action']} "
        f"resource={operation['resource_type']}::"
        f"{operation['resource_id']} "
        f"local_console={context['local_console']}"
    )

    if not allowed:
        LOG.warning("DENY %s", audit)
        print(
            f"cedudo: denied: {args.operation}",
            file=sys.stderr,
        )
        raise SystemExit(EX_NOPERM)

    argv = operation["argv"]
    LOG.info("PERMIT %s exec=%r", audit, argv)

    # Do not carry an attacker-controlled working directory or environment
    # into the privileged process.
    os.chdir("/")
    os.umask(0o022)

    try:
        os.execve(
            argv[0],
            argv,
            safe_environment(),
        )
    except OSError as exc:
        fail(
            f"authorized command could not be executed: {exc}",
            EX_SOFTWARE,
        )


if __name__ == "__main__":
    main()
```
