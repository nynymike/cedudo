# cedudo(1)

Cedar-authorized privilege wrapper — a restrictive `sudo`.

This is the manual for `cedudo`. The same text is printed by `cedudo --help`.

## Synopsis

```
cedudo <operation-id>
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

Extra arguments after the operation id are ignored — they cannot change the
fixed command — but they are logged so attempts are visible in the audit
trail.

## Operations

Operation ids are defined in `/opt/cedudo/operations.json`. The shipped
workshop manifest defines:

| Operation id | Action | Resource | Critical |
| --- | --- | --- | --- |
| `read-logs` | `read-logs` | `Linux::Service::"cedar-demo"` | no |
| `restart-demo` | `restart` | `Linux::Service::"cedar-demo"` | no |
| `restart-ssh` | `restart` | `Linux::Service::"ssh"` | yes |

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

| Field | Type | Meaning |
| --- | --- | --- |
| `current_time` | `Long` | Unix epoch seconds, from the US Central clock |
| `hour` | `Long` | Hour of day `0`–`23` in US Central time (`America/Chicago`) |
| `hostname` | `String` | Server hostname |
| `local_console` | `Bool` | `true` at a local console; `false` when the session looks remote (SSH) |
| `interactive` | `Bool` | `true` when stdin and stdout are a TTY |
| `intruder_risk_level` | `String` | Threat level; currently always `"low"` |

### Working with time

The **server clock** is the source of truth — callers cannot supply the time.
`hour` is pre-computed in US Central (`America/Chicago`, which tracks CST/CDT)
so policies need no date math. For finer control you can convert
`context.current_time` yourself.

```cedar
// permit only during business hours (09:00–16:59 Central)
when { context.hour >= 9 && context.hour < 17 }
```

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

**`forbid` always wins over `permit`.** Use a forbid to enforce a rule across
every grant, regardless of how many permits exist:

```cedar
@id("forbid-restart-outside-hours")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when { context.hour < 9 || context.hour >= 17 };
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

## See also

- The project `README.md` for installation and the workshop walkthrough.
- [Cedar policy language](https://www.cedarpolicy.com/)
- [Janssen Cedarling](https://docs.jans.io/stable/cedarling/)
