#!/opt/cedudo/venv/bin/python3
"""Workshop Cedar-authorized privilege wrapper (Policy Enforcement Point).

Usage:
    cedudo read-logs
    cedudo restart
    cedudo restart-ssh

The caller supplies only an operation ID. The command and every argument come
from a root-owned manifest at /opt/cedudo/operations.json. Authorization is
evaluated by Cedarling against the local Cedar Archive (.cjar) at
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
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

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
HELP_FLAGS = frozenset({"-h", "--h", "--help", "help"})

MANUAL = r"""NAME
    cedudo - Cedar-authorized privilege wrapper (a restrictive sudo)

SYNOPSIS
    cedudo <operation-id>
    cedudo --help

DESCRIPTION
    cedudo runs a fixed, root-owned privileged operation only if a Cedar
    policy allows it. The caller supplies one operation id. The actual
    command and all of its arguments come from a root-owned manifest at
    /opt/cedudo/operations.json -- never from the caller. Authorization is
    evaluated locally by Cedarling against the Cedar Archive (.cjar) at
    /opt/cedudo/cedudo.cjar.

    Any configuration, Cedarling, or policy-evaluation error fails closed:
    no privileged command is executed.

    This is educational software for learning Cedar authorization with
    privileged operations. It is not a production privilege manager.

OPTIONS
    -h, --h, --help
        Print this manual and exit. Works for any user, including root,
        and does not require the setuid installation.

    Extra arguments after the operation id are ignored (they cannot change
    the fixed command) but are logged so attempts are visible in the audit
    trail.

OPERATIONS
    Operation ids are defined in /opt/cedudo/operations.json. The shipped
    workshop manifest defines:

        read-logs      read-logs on Service "cedar-demo"  (noncritical)
        restart-demo   restart   on Service "cedar-demo"  (noncritical)
        restart-ssh    restart   on Service "ssh"         (critical)

    Run `cedudo <operation-id>`, for example `cedudo read-logs`. An id must
    match [a-z][a-z0-9-]{0,63}.

THE AUTHORIZATION REQUEST
    Every run builds one Cedar request of principal / action / resource /
    context:

      principal  Linux::User, derived from your real (not effective) uid.
                 Attributes available in policy:
                     uid    : Long
                     gid    : Long
                     groups : Set<String>   (your Linux group names)
                     home   : String
                     shell  : String

      action     Linux::Action, taken from the operation (e.g.
                 Linux::Action::"restart").

      resource   Linux::Service or Linux::Host from the operation.
                 Service attributes available in policy:
                     environment : String
                     critical    : Bool

      context    Runtime facts gathered by cedudo (see below).

CONTEXT (RUNTIME INFORMATION)
    cedudo sends these context fields on every request. Reference them in a
    policy as context.<name>. Guard optional fields with `context has <name>`
    before use.

        current_time         Long    Unix epoch seconds (US/Central clock).
        hour                 Long    Hour of day 0-23 in US Central time
                                     (America/Chicago). Use for business-hours
                                     rules.
        hostname             String  Server hostname.
        local_console        Bool    true at a local console; false when the
                                     session looks remote (SSH).
        interactive          Bool    true when stdin and stdout are a TTY.
        intruder_risk_level  String  Threat level; currently always "low".

    Working with time:
        The server clock is the source of truth; callers cannot supply the
        time. `hour` is pre-computed in US Central so policies need no date
        math. For finer control, convert context.current_time yourself.

        # permit only during business hours (09:00-16:59 Central)
        when { context.hour >= 9 && context.hour < 17 }

WRITING POLICIES ABOUT USERS AND GROUPS
    Policies live in the policy store and are packaged into the .cjar.
    Principals are Linux::User, so match on uid or group membership.

    Permit one Linux group to perform an action:

        @id("operators-restart")
        permit (
            principal is Linux::User,
            action == Linux::Action::"restart",
            resource
        )
        when {
            principal has groups &&
            principal.groups.contains("operators")
        };

    Combine principal, resource, and context conditions:

        permit (
            principal is Linux::User,
            action == Linux::Action::"restart",
            resource
        )
        when {
            principal.groups.contains("operators") &&
            resource has critical && !resource.critical &&
            context.intruder_risk_level == "low" &&
            context.hour >= 9 && context.hour < 17
        };

    Match a specific user instead of a group:

        when { principal == Linux::User::"alice" }

    Forbid always wins over permit. Use a forbid to enforce a rule across
    every grant, regardless of how many permits exist:

        @id("forbid-restart-outside-hours")
        forbid (
            principal,
            action == Linux::Action::"restart",
            resource
        )
        when { context.hour < 9 || context.hour >= 17 };

    Each .cedar file needs exactly one @id("...") annotation. After editing
    schema or policies, rebuild and redeploy the archive:

        tools/build-cjar.sh      # package policy/store into policy/cedudo.cjar
        tools/deploy-policy.sh   # install it to /opt/cedudo/cedudo.cjar

    If you add a new context field, declare it in BOTH schema.cedarschema
    and schema.json, under every action that receives it.

EXIT STATUS
    0    the authorized command executed (it replaces cedudo via exec)
    64   usage error (EX_USAGE)
    69   service unavailable, e.g. Cedarling error (EX_UNAVAILABLE)
    70   internal/software error (EX_SOFTWARE)
    77   denied or not permitted (EX_NOPERM)
    78   configuration error, e.g. untrusted manifest (EX_CONFIG)

FILES
    /opt/cedudo/cedudo            setuid-root wrapper binary
    /opt/cedudo/cedudo.py         this program
    /opt/cedudo/operations.json   root-owned operation manifest
    /opt/cedudo/cedudo.cjar       Cedar policy archive evaluated at runtime

SEE ALSO
    docs/cedudo.md in the repository, the project README, and the Cedar and
    Janssen Cedarling documentation.
"""


def print_manual() -> None:
    """Print the cedudo manual to stdout."""
    sys.stdout.write(MANUAL)
    if not MANUAL.endswith("\n"):
        sys.stdout.write("\n")

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


def cedar_uid(entity_type: str, entity_id: str) -> str:
    """Build a Cedar entity UID from separate type and id keys."""
    return f'{entity_type}::"{entity_id}"'


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
        "action_type",
        "action_id",
        "resource_type",
        "resource_id",
        "argv",
    }

    if not isinstance(operation, dict) or not required.issubset(operation):
        fail(
            f"invalid manifest entry for {operation_id}",
            EX_CONFIG,
        )

    action_type = operation["action_type"]
    action_id = operation["action_id"]
    resource_type = operation["resource_type"]
    resource_id = operation["resource_id"]
    argv = operation["argv"]

    if not isinstance(action_type, str) or not action_type:
        fail(f"invalid action_type for {operation_id}", EX_CONFIG)

    if not isinstance(action_id, str) or not action_id:
        fail(f"invalid action_id for {operation_id}", EX_CONFIG)

    if not isinstance(resource_type, str) or not resource_type:
        fail(f"invalid resource_type for {operation_id}", EX_CONFIG)

    if not isinstance(resource_id, str) or not resource_id:
        fail(f"invalid resource_id for {operation_id}", EX_CONFIG)

    operation["action"] = cedar_uid(action_type, action_id)

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

    # Derive time from the server clock in an explicit business timezone so
    # policies can enforce local business hours regardless of the server's
    # system timezone. America/Chicago tracks US Central time (CST/CDT).
    now = datetime.now(ZoneInfo("America/Chicago"))

    return {
        "current_time": int(now.timestamp()),
        "hour": now.hour,
        "hostname": socket.gethostname(),
        "local_console": not remote,
        "intruder_risk_level": "low",
        "interactive": os.isatty(0) and os.isatty(1),
    }


def initialize_cedarling() -> Cedarling:
    """Initialize Cedarling using only the trusted local .cjar store."""
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


def determining_policy_ids(diagnostics: Any) -> list[str]:
    """Return the policy ids Cedarling says determined the decision."""
    if diagnostics is None:
        return []
    reason = getattr(diagnostics, "reason", None) or ()
    return sorted(str(policy_id) for policy_id in reason)


def authorize(
    cedarling: Cedarling,
    account: pwd.struct_passwd,
    groups: list[str],
    operation: dict[str, Any],
    context: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Evaluate the unsigned Cedar authorization request.

    Returns whether the request is allowed and the policy ids that
    determined that decision. Evaluation errors fail closed.
    """
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
    except Exception as exc:
        fail(
            f"authorization evaluation failed: {exc}",
            EX_UNAVAILABLE,
        )

    # A decision alongside evaluation errors is not trustworthy. Cedarling
    # can still report Allow for the policies that did evaluate.
    diagnostics = getattr(getattr(result, "response", None), "diagnostics", None)
    errors = getattr(diagnostics, "errors", None) if diagnostics is not None else None
    if errors:
        details = "; ".join(
            f"{getattr(err, 'id', '?')}: {getattr(err, 'error', err)}"
            for err in errors
        )
        fail(
            f"Cedar policy evaluation errors: {details}",
            EX_UNAVAILABLE,
        )

    return bool(result.is_allowed()), determining_policy_ids(diagnostics)


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
    """Accept only the first positional operation ID.

    Trailing arguments cannot change the fixed argv from the manifest.
    They are logged and ignored so an attempt like ``--service ssh`` is
    visible in the audit trail.
    """
    if len(sys.argv) < 2:
        fail("usage: cedudo <operation-id>", EX_USAGE)

    operation = sys.argv[1]
    ignored = sys.argv[2:]
    if ignored:
        LOG.warning(
            "ignoring extra arguments: %s",
            " ".join(repr(arg) for arg in ignored),
        )

    if not OPERATION_RE.fullmatch(operation):
        fail(
            "operation must match [a-z][a-z0-9-]{0,63}",
            EX_USAGE,
        )

    return operation


def main() -> NoReturn:
    # Help must work for any user (including root) without the setuid
    # install, so handle it before any privilege or environment checks.
    if any(arg in HELP_FLAGS for arg in sys.argv[1:]):
        print_manual()
        raise SystemExit(0)

    operation_id = parse_operation()

    account, groups = invoking_user()
    operation = load_operation(operation_id)
    context = build_context()

    cedarling = initialize_cedarling()
    allowed, policy_ids = authorize(
        cedarling,
        account,
        groups,
        operation,
        context,
    )

    audit = (
        f"user={account.pw_name} "
        f"uid={account.pw_uid} "
        f"groups={groups} "
        f"operation={operation_id} "
        f"action={operation['action']} "
        f"resource={cedar_uid(operation['resource_type'], operation['resource_id'])} "
        f"local_console={context['local_console']} "
        f"interactive={context['interactive']} "
        f"intruder_risk_level={context['intruder_risk_level']} "
        f"policies={policy_ids}"
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
