# Sample Cedar policies

A reference library of example policies that exercise the runtime context
`cedudo` provides. See [`docs/cedudo.md`](../../docs/cedudo.md) for the full
list of principal, resource, and context attributes.

**These samples are not deployed.** `tools/build-cjar.sh` only packages
`policy/store/`, so nothing here affects the running demo or the README
walkthrough. To try one, copy it into `policy/store/policies/`, then rebuild
and redeploy:

```bash
cp policy/samples/<file>.cedar policy/store/policies/
tools/build-cjar.sh
tools/deploy-policy.sh
```

Each file carries exactly one `@id("...")` annotation, as the build requires.

## Trust reminder

`login_source_ip` and `auth_method` are environment-derived and can be forged
by a local user who controls their own environment. The samples that use them
always pair them with a trustworthy condition (group membership, day, hour).
Never make a forgeable signal the sole condition on a sensitive grant.

## What each sample demonstrates

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
