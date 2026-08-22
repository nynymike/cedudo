#!/opt/cedudo/venv/bin/python3
"""Workshop Cedar-authorized privilege wrapper (Policy Enforcement Point).

Usage:
    cedudo view-logs
    cedudo restart-demo

The caller supplies only an operation ID. The command and every argument come
from a root-owned manifest at /opt/cedudo/operations.json. Authorization is
evaluated by Cedarling against the AuthZEN Constraint JAR (.cjar) at
/opt/cedudo/cedudo.cjar.

This tool must be installed as a setuid-root executable to function properly.

Any Cedarling or configuration error fails closed (no privileged exec).

This is educational software for learning Cedar authorization with privileged operations.
It is not a production privilege management system.
"""

from __future__ import annotations

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
    """Configure stderr + optional syslog logging."""
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
    """Resolve the original user from real UID/GID (setuid execution)."""
    if os.geteuid() != 0:
        fail("must be installed as setuid root")

    # Get the real user ID (the user who invoked cedudo)
    uid = os.getuid()
    gid = os.getgid()

    if uid == 0:
        fail("direct root invocation is not a workshop principal")

    try:
        account = pwd.getpwuid(uid)
    except KeyError:
        fail("invoking user not found in account database")

    if account.pw_uid != uid or account.pw_gid != gid:
        fail("identity does not match the local account database")

    name = account.pw_name
    if name == "root":
        fail("direct root invocation is not a workshop principal")

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
    """Load and validate one fixed privileged operation from the manifest."""
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
    """Initialize Cedarling using only the trusted local AuthZEN .cjar store."""
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


def parse_operation() -> str:
    """Accept only the first positional operation ID; ignore trailing args."""
    if len(sys.argv) < 2:
        fail("usage: cedudo <operation-id>", EX_USAGE)

    operation = sys.argv[1]
    # Trailing arguments (e.g. --service ssh) are ignored by design so
    # injection attempts cannot change the fixed argv from the manifest.
    if not OPERATION_RE.fullmatch(operation):
        fail(
            "operation must match [a-z][a-z0-9-]{0,63}",
            EX_USAGE,
        )

    return operation


def main() -> NoReturn:
    operation_id = parse_operation()

    account, groups = invoking_user()
    operation = load_operation(operation_id)
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
        f"operation={operation_id} "
        f"action={operation['action']} "
        f"resource={operation['resource_type']}::"
        f"{operation['resource_id']} "
        f"local_console={context['local_console']}"
    )

    if not allowed:
        LOG.warning("DENY %s", audit)
        print(
            f"cedudo: denied: {operation_id}",
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
