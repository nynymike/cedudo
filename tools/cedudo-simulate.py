#!/usr/bin/env python3
"""Unprivileged Cedar decision simulator for the cedudo workshop.

This is a teaching aid, NOT the enforcement point. It never runs setuid, is
not installed to /opt/cedudo, and never executes any operation. Use it to
explore how a Cedar decision changes as you vary the principal identity and
the request context.

Unlike `cedudo explain`, which evaluates the real caller against the real
runtime context, this simulator lets you supply SYNTHETIC identities and
context overrides on the command line. That makes it safe for students to
answer "what if" questions without any privilege.

Examples:
    # Simulate bob (operators) restarting the demo on a weekday at 10:00
    tools/cedudo-simulate.py restart-demo \
        --user bob --uid 1001 --gid 1001 --groups operators \
        --hour 10 --day-of-week 2

    # Same, but over SSH after hours -> see a different decision
    tools/cedudo-simulate.py restart-demo \
        --user bob --groups operators \
        --local-console false --hour 22 --login-source-ip 203.0.113.7

    # Point at a different policy store
    tools/cedudo-simulate.py read-logs --user alice --groups developers \
        --policy-store /opt/cedudo/cedudo.cjar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

def _import_cedarling():
    """Import cedarling_python lazily so --help works without it installed."""
    try:
        from cedarling_python import (  # noqa: WPS433 (local import on purpose)
            BootstrapConfig,
            CedarEntityMapping,
            Cedarling,
            EntityData,
            RequestUnsigned,
        )
    except ImportError:
        sys.stderr.write(
            "error: cedarling_python is not installed in this interpreter.\n"
            "Install it (e.g. `pip install cedarling-python`) and retry.\n"
        )
        raise SystemExit(2)
    return (
        BootstrapConfig,
        CedarEntityMapping,
        Cedarling,
        EntityData,
        RequestUnsigned,
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = REPO_ROOT / "policy" / "cedudo.cjar"
DEFAULT_OPERATIONS = REPO_ROOT / "operations.json"


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "t", "yes", "y", "1"}:
        return True
    if lowered in {"false", "f", "no", "n", "0"}:
        return False
    raise argparse.ArgumentTypeError(f"expected a boolean, got {value!r}")


def load_operation(operations_file: Path, operation_id: str) -> dict[str, Any]:
    try:
        manifest = json.loads(operations_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read operations manifest: {exc}")

    if operation_id not in manifest:
        known = ", ".join(sorted(manifest)) or "(none)"
        raise SystemExit(
            f"error: unknown operation {operation_id!r}. Known: {known}"
        )

    op = dict(manifest[operation_id])
    op["action"] = f'{op["action_type"]}::"{op["action_id"]}"'
    op.setdefault("resource_attributes", {})
    return op


def default_context() -> dict[str, Any]:
    """A neutral weekday-business-hours local context students can override."""
    now = datetime.now(ZoneInfo("America/Chicago"))
    iso_weekday = now.isoweekday()
    return {
        "current_time": int(now.timestamp()),
        "hour": now.hour,
        "day_of_week": iso_weekday,
        "is_weekend": iso_weekday >= 6,
        "date": now.strftime("%Y-%m-%d"),
        "hostname": "workshop-vm",
        "intruder_risk_level": "low",
        "local_console": True,
        "is_remote": False,
        "interactive": True,
        "tty": "pts/0",
        "session_age_seconds": 120,
        "login_source_ip": "",
        "auth_method": "local",
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cedudo-simulate",
        description="Unprivileged Cedar decision simulator (never executes).",
    )
    p.add_argument("operation_id", help="operation id from the manifest")
    p.add_argument("--operations", type=Path, default=DEFAULT_OPERATIONS)
    p.add_argument("--policy-store", type=Path, default=DEFAULT_STORE)

    ident = p.add_argument_group("synthetic identity")
    ident.add_argument("--user", default="alice")
    ident.add_argument("--uid", type=int, default=1000)
    ident.add_argument("--gid", type=int, default=1000)
    ident.add_argument(
        "--groups",
        default="developers",
        help="comma-separated group names",
    )
    ident.add_argument("--home", default=None)
    ident.add_argument("--shell", default="/bin/bash")

    ctx = p.add_argument_group("context overrides")
    ctx.add_argument("--current-time", type=int)
    ctx.add_argument("--hour", type=int)
    ctx.add_argument("--day-of-week", type=int)
    ctx.add_argument("--is-weekend", type=parse_bool)
    ctx.add_argument("--date")
    ctx.add_argument("--hostname")
    ctx.add_argument("--intruder-risk-level")
    ctx.add_argument("--local-console", type=parse_bool)
    ctx.add_argument("--is-remote", type=parse_bool)
    ctx.add_argument("--interactive", type=parse_bool)
    ctx.add_argument("--tty")
    ctx.add_argument("--session-age-seconds", type=int)
    ctx.add_argument("--login-source-ip")
    ctx.add_argument("--auth-method")
    return p


# Map CLI dest -> context key for the override pass.
CTX_OVERRIDES = {
    "current_time": "current_time",
    "hour": "hour",
    "day_of_week": "day_of_week",
    "is_weekend": "is_weekend",
    "date": "date",
    "hostname": "hostname",
    "intruder_risk_level": "intruder_risk_level",
    "local_console": "local_console",
    "is_remote": "is_remote",
    "interactive": "interactive",
    "tty": "tty",
    "session_age_seconds": "session_age_seconds",
    "login_source_ip": "login_source_ip",
    "auth_method": "auth_method",
}


def fingerprint(store: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(store.read_bytes()).hexdigest()[:16]
    except OSError as exc:
        return f"unavailable ({exc})"


def main() -> int:
    args = build_parser().parse_args()

    store = args.policy_store
    if not store.is_file():
        raise SystemExit(f"error: policy store not found: {store}")

    operation = load_operation(args.operations, args.operation_id)

    groups = [g for g in args.groups.split(",") if g]
    home = args.home or f"/home/{args.user}"

    context = default_context()
    for dest, key in CTX_OVERRIDES.items():
        value = getattr(args, dest)
        if value is not None:
            context[key] = value
    # Keep is_remote/local_console consistent if only one was given.
    if getattr(args, "local_console") is not None and args.is_remote is None:
        context["is_remote"] = not args.local_console
    elif args.is_remote is not None and args.local_console is None:
        context["local_console"] = not args.is_remote

    import os

    (
        BootstrapConfig,
        CedarEntityMapping,
        Cedarling,
        EntityData,
        RequestUnsigned,
    ) = _import_cedarling()

    os.environ["CEDARLING_POLICY_STORE_LOCAL_FN"] = str(store)
    os.environ["CEDARLING_APPLICATION_NAME"] = "cedudo-simulate"
    try:
        cedarling = Cedarling(BootstrapConfig.from_env())
    except Exception as exc:
        raise SystemExit(f"error: Cedarling initialization failed: {exc}")

    principal = EntityData(
        cedar_entity_mapping=CedarEntityMapping(
            entity_type="Linux::User", id=args.user
        ),
        uid=args.uid,
        gid=args.gid,
        groups=groups,
        home=home,
        shell=args.shell,
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
        raise SystemExit(f"error: authorization evaluation failed: {exc}")

    diagnostics = getattr(
        getattr(result, "response", None), "diagnostics", None
    )
    reason = getattr(diagnostics, "reason", None) or ()
    policy_ids = sorted(str(pid) for pid in reason)
    errors = getattr(diagnostics, "errors", None) or ()
    allowed = bool(result.is_allowed())

    resource_uid = (
        f'{operation["resource_type"]}::"{operation["resource_id"]}"'
    )

    out = sys.stdout.write
    out("cedudo-simulate (SYNTHETIC -- unprivileged, never executes)\n\n")
    out("Synthetic identity\n")
    out(f"  user   : {args.user} (uid {args.uid}, gid {args.gid})\n")
    out(f"  groups : {', '.join(groups) if groups else '(none)'}\n\n")
    out("Operation to Cedar request\n")
    out(f"  operation id : {args.operation_id}\n")
    out(f"  cedar action : {operation['action']}\n")
    out(f"  cedar resource: {resource_uid}\n\n")
    out("Context\n")
    width = max(len(k) for k in context)
    for key in context:
        out(f"  {key.ljust(width)} = {context[key]!r}\n")
    out("\n")
    out(f"Policy store: {store}\n")
    out(f"  fingerprint: {fingerprint(store)}\n\n")
    out("Decision\n")
    out(f"  result          : {'ALLOW' if allowed else 'DENY'}\n")
    out(
        f"  determining ids : "
        f"{', '.join(policy_ids) if policy_ids else '(none)'}\n"
    )
    if errors:
        out("  evaluation errors:\n")
        for err in errors:
            eid = getattr(err, "id", "?")
            emsg = getattr(err, "error", err)
            out(f"    - {eid}: {emsg}\n")
    else:
        out("  evaluation errors: (none)\n")
    out("\nNote: this simulator never runs the operation's command.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
