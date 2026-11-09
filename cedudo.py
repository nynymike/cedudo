#!/opt/cedudo/venv/bin/python3
"""Workshop Cedar-authorized privilege wrapper (Policy Enforcement Point).

Usage:
    cedudo read-logs
    cedudo restart-demo
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
import hashlib
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
    cedudo explain <operation-id>
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

    explain <operation-id>
        Dry run. Print the full Linux-to-Cedar translation for the operation
        -- identity (real and effective uid/gid, username, groups), the
        Cedar action and resource, every context value and where it came
        from, the policy-store fingerprint, the decision with its
        determining policy ids and any evaluation errors, and the fixed
        command that WOULD run. The operation is NEVER executed.

        `explain` uses the real caller and the real runtime context. To try
        synthetic identities or context overrides ("what if bob ran this
        over SSH at 22:00?"), use the unprivileged simulator instead:

            tools/cedudo-simulate.py <operation-id> --user bob \
                --groups operators --local-console false --hour 22

        The simulator is not setuid, is not installed to /opt/cedudo, and
        also never executes anything.

    Extra arguments after the operation id are ignored (they cannot change
    the fixed command) but are logged so attempts are visible in the audit
    trail.

OPERATIONS
    Operation ids are defined in /opt/cedudo/operations.json. The shipped
    workshop manifest defines:

        read-logs      read-logs on Service "cedar-demo"  (noncritical)
                       REAL: last 20 journal entries of cedar-demo.service
        restart-demo   restart   on Service "cedar-demo"  (noncritical)
                       REAL: systemctl restart cedar-demo.service
        restart-ssh    restart   on Service "ssh"         (critical)
                       SIMULATED: prints a message; ssh is never restarted

    Run `cedudo <operation-id>`, for example `cedudo restart-demo`. An id must
    match [a-z][a-z0-9-]{0,63}. Several operations can share one Cedar action
    (restart-demo and restart-ssh both use `restart`).

    An id that is not in the manifest (for example `root-shell`) is rejected
    before Cedar runs. A permit only means Cedar allowed the request: the
    fixed command can still fail, and that failure is the command's own.
    Check the result, e.g. `systemctl show cedar-demo.service -p InvocationID`.

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

    Time (server clock, US Central; trustworthy):
        current_time         Long    Unix epoch seconds.
        hour                 Long    Hour of day 0-23 (America/Chicago).
        day_of_week          Long    ISO weekday 1-7 (1=Mon ... 7=Sun).
        is_weekend           Bool    true on Saturday or Sunday.
        date                 String  Calendar date "YYYY-MM-DD" (Central).

    Host and posture:
        hostname             String  Server hostname.
        intruder_risk_level  String  Threat level; currently always "low".

    Session shape (kernel/TTY-derived; reasonably trustworthy):
        local_console        Bool    true at a local console.
        is_remote            Bool    true when the session looks remote (SSH).
        interactive          Bool    true when stdin and stdout are a TTY.
        tty                  String  Controlling terminal (e.g. "pts/0"),
                                     "" if none.
        session_age_seconds  Long    Seconds since the session leader
                                     started; -1 if unknown.

    Weak signals (environment-derived; ADVISORY ONLY, forgeable by a local
    user who controls their own environment -- do not use as a sole gate):
        login_source_ip      String  Remote client IP from SSH_CONNECTION,
                                     "" if local/unknown.
        auth_method          String  "oidc" | "pubkey" | "password" |
                                     "local" | "unknown".

    Working with time:
        The server clock is the source of truth; callers cannot supply the
        time. `hour`, `day_of_week`, `is_weekend`, and `date` are pre-computed
        in US Central so policies need no date math. For finer control,
        convert context.current_time yourself.

        # permit only during business hours on weekdays (Mon-Fri, 09:00-16:59)
        when {
            context.day_of_week <= 5 &&
            context.hour >= 9 && context.hour < 17
        }

    Trust note:
        Fields in the time, host, and session groups derive from the server
        clock, account database, or kernel and are trustworthy. login_source_ip
        and auth_method come from environment variables set by sshd/PAM; a user
        who controls their own environment can forge them. Use them as
        defense-in-depth, not as the only condition on a sensitive grant.

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

    Use context to restrict by day, network, or auth method:

        # only operators who authenticated via OIDC (advisory) may restart
        when {
            principal.groups.contains("operators") &&
            context.auth_method == "oidc"
        }

        # restart only from the management subnet (advisory signal)
        when { context.login_source_ip like "10.0.0.*" }

        # no privileged ops in the first 5 seconds of a session
        when { context.session_age_seconds >= 5 }

    Forbid always wins over permit. Use a forbid to enforce a rule across
    every grant, regardless of how many permits exist:

        @id("forbid-restart-outside-hours")
        forbid (
            principal,
            action == Linux::Action::"restart",
            resource
        )
        when {
            context.is_weekend ||
            context.hour < 9 || context.hour >= 17
        };

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
    tools/cedudo-simulate.py      unprivileged "what if" decision simulator

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


def login_source_ip() -> str:
    """Best-effort remote client IP for the session.

    Parsed from SSH_CONNECTION (``<client_ip> <client_port> <server_ip>
    <server_port>``), falling back to SSH_CLIENT. Returns "" when the
    session is local or the value is unavailable.

    WEAK SIGNAL: these environment variables are set by sshd but are not
    guaranteed and can be forged by a user who controls their own
    environment. Treat as advisory, not as a security boundary.
    """
    for var in ("SSH_CONNECTION", "SSH_CLIENT"):
        value = os.environ.get(var, "").strip()
        if value:
            candidate = value.split()[0]
            try:
                socket.inet_pton(socket.AF_INET, candidate)
                return candidate
            except OSError:
                pass
            try:
                socket.inet_pton(socket.AF_INET6, candidate)
                return candidate
            except OSError:
                pass
    return ""


def controlling_tty() -> str:
    """Best-effort controlling terminal name, e.g. "pts/0". "" if none.

    The leading "/dev/" is stripped so policy authors can match on the
    familiar short form (e.g. `context.tty like "pts/*"`).
    """
    for fd in (0, 1, 2):
        try:
            name = os.ttyname(fd)
        except OSError:
            continue
        prefix = "/dev/"
        return name[len(prefix):] if name.startswith(prefix) else name
    return ""


def auth_method() -> str:
    """Best-effort authentication method for this session.

    Derived from PAM environment hints when present, otherwise inferred
    coarsely from the session shape. Returns one of "oidc", "pubkey",
    "password", "local", or "unknown".

    WEAK SIGNAL: PAM_* variables are not reliably exported to the final
    user environment and can be set by a user who controls their own
    environment. Treat as advisory, not as a security boundary.
    """
    pam_service = os.environ.get("PAM_SERVICE", "").lower()
    pam_type = os.environ.get("PAM_TYPE", "").lower()

    if "authd" in pam_service or "oidc" in pam_service:
        return "oidc"
    if pam_type in {"auth", "open_session"} and pam_service:
        # A PAM session exists but the method is not distinguishable here.
        return "password"
    if os.environ.get("SSH_AUTH_INFO_0", "").lower().startswith("publickey"):
        return "pubkey"
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        return "unknown"
    return "local"


def session_age_seconds() -> int:
    """Best-effort seconds since the controlling session leader started.

    Uses the start time of the session leader process (getsid) from
    /proc/<pid>/stat relative to system boot. Returns -1 when it cannot be
    determined (e.g. no /proc, or an unreadable field).
    """
    try:
        sid = os.getsid(0)
        clock_ticks = os.sysconf("SC_CLK_TCK")
        if clock_ticks <= 0:
            return -1

        with open("/proc/uptime", encoding="utf-8") as fh:
            uptime = float(fh.read().split()[0])

        stat_text = Path(f"/proc/{sid}/stat").read_text(encoding="utf-8")
        # Field 22 (1-indexed) is starttime, in clock ticks since boot.
        # The comm field may contain spaces/parens, so split after the ')'.
        after_comm = stat_text.rsplit(")", 1)[1].split()
        starttime_ticks = int(after_comm[19])
        start_seconds = starttime_ticks / clock_ticks
        age = int(uptime - start_seconds)
        return age if age >= 0 else 0
    except (OSError, ValueError, IndexError, AttributeError):
        return -1


def build_context() -> dict[str, Any]:
    """Build authorization context from the execution environment."""
    source_ip = login_source_ip()
    remote = bool(
        source_ip
        or os.environ.get("SSH_CONNECTION")
        or os.environ.get("SSH_CLIENT")
        or "sshd" in ancestor_names(os.getppid())
    )

    # Derive time from the server clock in an explicit business timezone so
    # policies can enforce local business hours regardless of the server's
    # system timezone. America/Chicago tracks US Central time (CST/CDT).
    now = datetime.now(ZoneInfo("America/Chicago"))
    iso_weekday = now.isoweekday()  # 1 = Monday ... 7 = Sunday

    return {
        # Time (server clock, US Central). Trustworthy.
        "current_time": int(now.timestamp()),
        "hour": now.hour,
        "day_of_week": iso_weekday,
        "is_weekend": iso_weekday >= 6,
        "date": now.strftime("%Y-%m-%d"),
        # Host and threat posture.
        "hostname": socket.gethostname(),
        "intruder_risk_level": "low",
        # Session shape.
        "local_console": not remote,
        "is_remote": remote,
        "interactive": os.isatty(0) and os.isatty(1),
        "tty": controlling_tty(),
        "session_age_seconds": session_age_seconds(),
        # Weak, environment-derived signals (advisory only).
        "login_source_ip": source_ip,
        "auth_method": auth_method(),
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


def evaluation_errors(diagnostics: Any) -> list[str]:
    """Return human-readable Cedar evaluation error strings, if any."""
    if diagnostics is None:
        return []
    errors = getattr(diagnostics, "errors", None) or ()
    return [
        f"{getattr(err, 'id', '?')}: {getattr(err, 'error', err)}"
        for err in errors
    ]


def build_request(
    account: pwd.struct_passwd,
    groups: list[str],
    operation: dict[str, Any],
    context: dict[str, Any],
) -> RequestUnsigned:
    """Build the unsigned Cedar request from identity, operation, context."""
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

    return RequestUnsigned(
        principal=principal,
        action=operation["action"],
        resource=resource,
        context=context,
    )


def evaluate(
    cedarling: Cedarling,
    request: RequestUnsigned,
) -> tuple[bool, list[str], list[str]]:
    """Evaluate a request, returning (allowed, policy_ids, errors).

    This does NOT fail closed on evaluation errors; callers decide how to
    treat a decision that was accompanied by errors. The ``explain`` path
    needs to surface those errors rather than abort.
    """
    try:
        result = cedarling.authorize_unsigned(request)
    except Exception as exc:
        fail(
            f"authorization evaluation failed: {exc}",
            EX_UNAVAILABLE,
        )

    diagnostics = getattr(
        getattr(result, "response", None), "diagnostics", None
    )
    return (
        bool(result.is_allowed()),
        determining_policy_ids(diagnostics),
        evaluation_errors(diagnostics),
    )


def authorize(
    cedarling: Cedarling,
    account: pwd.struct_passwd,
    groups: list[str],
    operation: dict[str, Any],
    context: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Evaluate the unsigned Cedar authorization request for the exec path.

    Returns whether the request is allowed and the policy ids that
    determined that decision. Evaluation errors fail closed: a decision
    reported alongside errors is not trustworthy for a privileged exec.
    """
    request = build_request(account, groups, operation, context)
    allowed, policy_ids, errors = evaluate(cedarling, request)

    if errors:
        fail(
            f"Cedar policy evaluation errors: {'; '.join(errors)}",
            EX_UNAVAILABLE,
        )

    return allowed, policy_ids


# Where each context field comes from, for the `explain` report. Keep in
# sync with build_context().
CONTEXT_SOURCES: dict[str, str] = {
    "current_time": "server clock (US Central), epoch seconds",
    "hour": "server clock (US Central), hour 0-23",
    "day_of_week": "server clock (US Central), ISO weekday 1-7",
    "is_weekend": "derived from day_of_week",
    "date": "server clock (US Central), YYYY-MM-DD",
    "hostname": "socket.gethostname()",
    "intruder_risk_level": "fixed policy input (currently always 'low')",
    "local_console": "derived: not remote (see is_remote)",
    "is_remote": "SSH_CONNECTION/SSH_CLIENT env or sshd ancestor in /proc",
    "interactive": "os.isatty(stdin) and os.isatty(stdout)",
    "tty": "os.ttyname() of a std fd",
    "session_age_seconds": "session leader start time from /proc",
    "login_source_ip": "SSH_CONNECTION env [WEAK: forgeable]",
    "auth_method": "PAM_*/SSH env hints [WEAK: forgeable]",
}


def policy_store_fingerprint() -> str:
    """Return a short SHA-256 fingerprint of the policy-store archive."""
    try:
        digest = hashlib.sha256(POLICY_STORE.read_bytes()).hexdigest()
        return f"sha256:{digest[:16]}"
    except OSError as exc:
        return f"unavailable ({exc})"


def explain_operation(operation_id: str) -> NoReturn:
    """Print the full Linux-to-Cedar translation for an operation and exit.

    This NEVER executes the operation. It evaluates authorization against
    the real caller identity and the real runtime context, then prints a
    structured report so students can see exactly how a Linux invocation
    becomes a Cedar request and decision. For synthetic identities or
    context overrides, use the unprivileged simulator
    (tools/cedudo-simulate.py) instead.
    """
    account, groups = invoking_user()
    operation = load_operation(operation_id)
    context = build_context()

    cedarling = initialize_cedarling()
    request = build_request(account, groups, operation, context)
    allowed, policy_ids, errors = evaluate(cedarling, request)

    resource_uid = cedar_uid(
        operation["resource_type"], operation["resource_id"]
    )

    out = sys.stdout.write
    out(f"cedudo explain: {operation_id}\n")
    out("(dry run -- the operation is NOT executed)\n\n")

    out("Identity\n")
    out(f"  real uid/gid     : {os.getuid()}/{os.getgid()}\n")
    out(f"  effective uid/gid: {os.geteuid()}/{os.getegid()}\n")
    out(f"  username         : {account.pw_name}\n")
    out(f"  groups           : {', '.join(groups) if groups else '(none)'}\n")
    out(f"  home / shell     : {account.pw_dir} / {account.pw_shell}\n\n")

    out("Operation to Cedar request\n")
    out(f"  operation id     : {operation_id}\n")
    out(f"  cedar action     : {operation['action']}\n")
    out(f"  cedar resource   : {resource_uid}\n")
    res_attrs = operation.get("resource_attributes") or {}
    if res_attrs:
        pairs = ", ".join(f"{k}={v!r}" for k, v in sorted(res_attrs.items()))
        out(f"  resource attrs   : {pairs}\n")
    out("\n")

    out("Context (value <- source)\n")
    width = max(len(k) for k in context)
    for key in context:
        source = CONTEXT_SOURCES.get(key, "(source unknown)")
        out(f"  {key.ljust(width)} = {context[key]!r}  <- {source}\n")
    out("\n")

    out("Policy store\n")
    out(f"  path             : {POLICY_STORE}\n")
    out(f"  fingerprint      : {policy_store_fingerprint()}\n\n")

    out("Decision\n")
    out(f"  result           : {'ALLOW' if allowed else 'DENY'}\n")
    out(
        f"  determining ids  : "
        f"{', '.join(policy_ids) if policy_ids else '(none)'}\n"
    )
    if errors:
        out("  evaluation errors:\n")
        for err in errors:
            out(f"    - {err}\n")
    else:
        out("  evaluation errors: (none)\n")
    out("\n")

    out("Command that WOULD run (not executed)\n")
    out(f"  argv             : {operation['argv']}\n")

    raise SystemExit(0)


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


def validate_operation_id(operation: str) -> str:
    """Return the operation id if it matches the allowed format, else fail."""
    if not OPERATION_RE.fullmatch(operation):
        fail(
            "operation must match [a-z][a-z0-9-]{0,63}",
            EX_USAGE,
        )
    return operation


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

    return validate_operation_id(operation)


def main() -> NoReturn:
    # Help must work for any user (including root) without the setuid
    # install, so handle it before any privilege or environment checks.
    if any(arg in HELP_FLAGS for arg in sys.argv[1:]):
        print_manual()
        raise SystemExit(0)

    # `cedudo explain <operation-id>` is a read-only dry run: it prints the
    # Linux-to-Cedar translation and decision but never executes anything.
    if len(sys.argv) >= 2 and sys.argv[1] == "explain":
        if len(sys.argv) < 3:
            fail("usage: cedudo explain <operation-id>", EX_USAGE)
        if len(sys.argv) > 3:
            LOG.warning(
                "ignoring extra arguments: %s",
                " ".join(repr(arg) for arg in sys.argv[3:]),
            )
        explain_operation(validate_operation_id(sys.argv[2]))

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
        f"day_of_week={context['day_of_week']} "
        f"date={context['date']} "
        f"source_ip={context['login_source_ip'] or '-'} "
        f"auth_method={context['auth_method']} "
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
