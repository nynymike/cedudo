# cedudo(1)

Cedar-authorized privilege wrapper — a restrictive `sudo`.

This is the manual for `cedudo`. The same text is printed by `cedudo --help`.

## Synopsis

```
cedudo <operation-id>
cedudo explain <operation-id>
cedudo --help
```

## Description

`cedudo` runs a fixed, root-owned privileged operation **only if a Cedar
policy allows it**. The caller supplies one operation id. The actual command
and all of its arguments come from a root-owned manifest at
`/opt/cedudo/operations.json` — never from the caller. Authorization is
evaluated locally by [Cedarling](https://docs.jans.io/stable/cedarling/)
against the Cedar Archive (`.cjar`) at `/opt/cedudo/cedudo.cjar`.

Any configuration, Cedarling, or policy-evaluation error **fails closed**: no
privileged command is executed.

> This is educational software for learning Cedar authorization with
> privileged operations. It is not a production privilege manager.

## Options

| Option | Effect |
| --- | --- |
| `-h`, `--h`, `--help`, `help` | Print this manual and exit. Works for any user, including root, and does not require the setuid installation. |
| `explain <operation-id>` | Dry run: print the full Linux-to-Cedar translation and decision **without executing** the operation. See [Explaining decisions](#explaining-decisions). |

Extra arguments after the operation id are ignored — they cannot change the
fixed command — but they are logged so attempts are visible in the audit
trail.

## Explaining decisions

`cedudo explain <operation-id>` is a read-only **dry run**. It evaluates
authorization for the real caller against the real runtime context and prints
the whole translation, then exits — **the operation is never executed**. It is
the fastest way for students to see how a Linux invocation becomes a Cedar
request and decision.

The report shows:

- **Identity** — real and effective uid/gid, resolved username, groups, home,
  and shell.
- **Operation → Cedar request** — operation id, Cedar action, resource, and
  resource attributes.
- **Context** — every context value and the source it was derived from (server
  clock, kernel/TTY, account database, or forgeable environment variable).
- **Policy store** — path and a SHA-256 fingerprint of the deployed `.cjar`.
- **Decision** — ALLOW/DENY, the determining policy ids, and any Cedar
  evaluation errors.
- **Command** — the fixed `argv` that *would* run.

```bash
cedudo explain restart-demo
```

### Simulating "what if" scenarios

`explain` only reports the real caller and real context. To explore how the
decision changes for a **different identity** or a **different context** —
"what if bob ran this over SSH at 22:00?" — use the unprivileged simulator,
which is **not** setuid, is **not** installed to `/opt/cedudo`, and also never
executes anything:

```bash
# bob (operators) restarting the demo after hours over SSH
tools/cedudo-simulate.py restart-demo \
    --user bob --uid 1001 --gid 1001 --groups operators \
    --local-console false --hour 22 --login-source-ip 203.0.113.7
```

It accepts synthetic identity flags (`--user`, `--uid`, `--gid`, `--groups`,
`--home`, `--shell`) and a context override for every field (`--hour`,
`--day-of-week`, `--is-weekend`, `--date`, `--local-console`, `--is-remote`,
`--auth-method`, `--login-source-ip`, and the rest). It defaults to the repo's
`policy/cedudo.cjar`; use `--policy-store` to point elsewhere.

> Keeping synthetic identities and context overrides in the unprivileged
> simulator — never in the setuid `cedudo` binary — means a student can never
> use a "what if" flag to influence a real privileged decision.

## Operations

Operation ids are defined in `/opt/cedudo/operations.json`. The shipped
workshop manifest defines:

| Operation id | Action | Resource | Critical | Execution |
| --- | --- | --- | --- | --- |
| `read-logs` | `read-logs` | `Linux::Service::"cedar-demo"` | no | Real: `journalctl --unit=cedar-demo.service --lines=20 --no-pager` |
| `restart-demo` | `restart` | `Linux::Service::"cedar-demo"` | no | Real: `systemctl restart cedar-demo.service` |
| `restart-ssh` | `restart` | `Linux::Service::"ssh"` | yes | Simulated: prints a message, never restarts SSH |

`root-shell` is deliberately absent from the manifest, so it is rejected before
Cedar runs. The Tarp example `examples/root-shell.json` is separate: it sends
the Cedar action `open-shell` to the policy store, where `forbid-open-shell`
denies it. A `PERMIT` only means Cedar allowed the request; the fixed command
can still fail, so verify the result (for example the service's `InvocationID`).

Run an operation by id:

```bash
cedudo read-logs
```

An id must match `[a-z][a-z0-9-]{0,63}`.

## The authorization request

Every run builds exactly one Cedar request of **principal / action / resource
/ context**:

- **principal** — `Linux::User`, derived from your *real* (not effective)
  uid. Attributes available in policy:

  | Attribute | Type | Meaning |
  | --- | --- | --- |
  | `uid` | `Long` | Numeric user id |
  | `gid` | `Long` | Primary group id |
  | `groups` | `Set<String>` | Your Linux group names |
  | `home` | `String` | Home directory |
  | `shell` | `String` | Login shell |

- **action** — `Linux::Action`, taken from the operation (e.g.
  `Linux::Action::"restart"`).

- **resource** — `Linux::Service` or `Linux::Host` from the operation.
  Service attributes available in policy:

  | Attribute | Type | Meaning |
  | --- | --- | --- |
  | `environment` | `String` | e.g. `"workshop"` |
  | `critical` | `Bool` | Whether the service is critical |

- **context** — runtime facts gathered by `cedudo` (below).

## Context (runtime information)

`cedudo` sends these context fields on **every** request. Reference them in a
policy as `context.<name>`. Guard optional fields with `context has <name>`
before use.

**Time** (server clock, US Central — trustworthy):

| Field | Type | Meaning |
| --- | --- | --- |
| `current_time` | `Long` | Unix epoch seconds |
| `hour` | `Long` | Hour of day `0`–`23` (`America/Chicago`) |
| `day_of_week` | `Long` | ISO weekday `1`–`7` (1 = Monday … 7 = Sunday) |
| `is_weekend` | `Bool` | `true` on Saturday or Sunday |
| `date` | `String` | Calendar date `YYYY-MM-DD` (Central) |

**Host and posture:**

| Field | Type | Meaning |
| --- | --- | --- |
| `hostname` | `String` | Server hostname |
| `intruder_risk_level` | `String` | Threat level; currently always `"low"` |

**Session shape** (kernel/TTY-derived — reasonably trustworthy):

| Field | Type | Meaning |
| --- | --- | --- |
| `local_console` | `Bool` | `true` at a local console |
| `is_remote` | `Bool` | `true` when the session looks remote (SSH) |
| `interactive` | `Bool` | `true` when stdin and stdout are a TTY |
| `tty` | `String` | Controlling terminal (e.g. `"pts/0"`), `""` if none |
| `session_age_seconds` | `Long` | Seconds since the session leader started; `-1` if unknown |

**Weak signals** (environment-derived — **advisory only**, forgeable by a
local user who controls their own environment; never use as a sole gate):

| Field | Type | Meaning |
| --- | --- | --- |
| `login_source_ip` | `String` | Remote client IP from `SSH_CONNECTION`, `""` if local/unknown |
| `auth_method` | `String` | `"oidc"` \| `"pubkey"` \| `"password"` \| `"local"` \| `"unknown"` |

### Working with time

The **server clock** is the source of truth — callers cannot supply the time.
`hour`, `day_of_week`, `is_weekend`, and `date` are pre-computed in US Central
(`America/Chicago`, which tracks CST/CDT) so policies need no date math. For
finer control you can convert `context.current_time` yourself.

```cedar
// permit only during business hours on weekdays (Mon–Fri, 09:00–16:59)
when {
    context.day_of_week <= 5 &&
    context.hour >= 9 && context.hour < 17
}
```

### Trust note

Fields in the **time**, **host**, and **session** groups derive from the
server clock, the account database, or the kernel and are trustworthy.
`login_source_ip` and `auth_method` come from environment variables set by
sshd and PAM; a user who controls their own environment can forge them. Use
them as **defense-in-depth**, not as the only condition on a sensitive grant.

## Writing policies about users and groups

Policies live in `policy/store/policies/*.cedar` and are packaged into the
`.cjar`. Principals are `Linux::User`, so match on `uid` or group membership.

**Permit one Linux group to perform an action:**

```cedar
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
```

**Combine principal, resource, and context conditions:**

```cedar
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
```

**Match a specific user instead of a group:**

```cedar
when { principal == Linux::User::"alice" }
```

**Restrict by day, network, or auth method** using context:

```cedar
// only operators who authenticated via OIDC (advisory) may restart
when {
    principal.groups.contains("operators") &&
    context.auth_method == "oidc"
}

// restart only from the management subnet (advisory signal)
when { context.login_source_ip like "10.0.0.*" }

// no privileged ops in the first 5 seconds of a session
when { context.session_age_seconds >= 5 }
```

> `login_source_ip` and `auth_method` are advisory, forgeable signals (see the
> trust note above). Pair them with a trustworthy condition rather than
> relying on them alone.

**`forbid` always wins over `permit`.** Use a forbid to enforce a rule across
every grant, regardless of how many permits exist:

```cedar
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
```

Each `.cedar` file needs exactly one `@id("...")` annotation.

After editing the schema or policies, rebuild and redeploy the archive:

```bash
tools/build-cjar.sh      # package policy/store into policy/cedudo.cjar
tools/deploy-policy.sh   # install it to /opt/cedudo/cedudo.cjar
```

> If you add a new context field, declare it in **both**
> `schema.cedarschema` and `schema.json`, under **every** action that
> receives it. `cedudo` sends the same context dictionary for all actions, so
> a field missing from any action's schema will fail validation.

## Exit status

| Code | Name | Meaning |
| --- | --- | --- |
| `0` | — | The authorized command executed (it replaces `cedudo` via `exec`) |
| `64` | `EX_USAGE` | Usage error |
| `69` | `EX_UNAVAILABLE` | Service unavailable, e.g. a Cedarling error |
| `70` | `EX_SOFTWARE` | Internal / software error |
| `77` | `EX_NOPERM` | Denied or not permitted |
| `78` | `EX_CONFIG` | Configuration error, e.g. an untrusted manifest |

## Files

| Path | Purpose |
| --- | --- |
| `/opt/cedudo/cedudo` | setuid-root wrapper binary |
| `/opt/cedudo/cedudo.py` | This program |
| `/opt/cedudo/operations.json` | Root-owned operation manifest |
| `/opt/cedudo/cedudo.cjar` | Cedar policy archive evaluated at runtime |

## Sample policies

A reference library covering most of the context fields lives in
[`policy/samples/`](../policy/samples/) (see its `README.md`). These samples
are **not deployed** — the build only packages `policy/store/` — so copy one
into `policy/store/policies/` and rebuild to try it:

| File | Kind | Context used |
| --- | --- | --- |
| `permit-weekday-business-hours.cedar` | permit | `day_of_week`, `hour` |
| `permit-operators-oidc-restart.cedar` | permit | `auth_method`, groups |
| `permit-restart-from-mgmt-subnet.cedar` | permit | `login_source_ip`, groups |
| `permit-read-logs-local-console.cedar` | permit | `local_console`, `interactive`, `tty` |
| `forbid-restart-on-weekend.cedar` | forbid | `is_weekend` |
| `forbid-change-freeze-date.cedar` | forbid | `date` |
| `forbid-restart-fresh-session.cedar` | forbid | `session_age_seconds` |
| `forbid-restart-elevated-risk.cedar` | forbid | `intruder_risk_level` |
| `forbid-restart-wrong-host.cedar` | forbid | `hostname` |

## See also

- The project `README.md` for installation and the workshop walkthrough.
- [`tools.md`](tools.md) for a reference to every command and script.
- [Cedar policy language](https://www.cedarpolicy.com/)
- [Janssen Cedarling](https://docs.jans.io/stable/cedarling/)
