# Build a Safer Privilege System with Cedar

An 80-minute hands-on workshop. You will authorize privileged Linux operations
with [Cedar](https://www.cedarpolicy.com/) policies, test them in the browser
with Tarp, then enforce the same policies on a Linux VM through a Cedar-authorized
privilege wrapper called `cedudo`.

`cedudo` is a setuid-root executable that uses Cedar policies for authorization.

**This is educational software for learning Cedar authorization. Not for production use.**

By the end you will:

- Model a Linux privilege as a Cedar **principal / action / resource / context** request
- Test permit and deny decisions in Tarp before touching the VM
- Change a Cedar policy and reload the shared policy store
- See the same policy control a real `systemctl` / `journalctl` operation
- Try common bypasses and see why they fail

Read this document from top to bottom: prepare the day before, show up ready,
then follow the class sections in order.

---

## The day before

Do this the evening before so class time is not spent on downloads.

### 1. Get the workshop VM

You need the prepared Ubuntu/Debian workshop image provided by the facilitators
(download link and checksum will be in the event materials). Import it into
VirtualBox, VMware, UTM, or your usual hypervisor.

Do **not** spend time installing Cedar, Tarp, or Python packages yourself. The
VM already has:

- Tarp (browser extension / package)
- Cedarling Python bindings
- The `cedar-demo` systemd service
- `cedudo` installed under `/opt/cedudo/` (includes the C wrapper for setuid support)
- Workshop files under `~/cedudo-workshop/` (or this repository checked out there)

### 2. Install a desktop browser (on the VM or host, as instructed)

Tarp runs in Chrome or Firefox. Confirm you can open the browser on the path
the facilitators describe for your event (often inside the VM).

### 3. Skim the mental model (5 minutes)

Two components work together:

| Piece | Job |
|-------|-----|
| **cedudo (setuid)** | Policy Enforcement Point: accept an operation ID, ask Cedar, run a **fixed** command with elevated privileges |
| **Cedarling** | Policy Decision Point: evaluate Cedar policies and return permit or deny |

Tarp is the browser workbench. Both Tarp and `cedudo` load the **same** policy
store file: `cedudo.cjar` (a Cedar Archive—a ZIP of policies, schema,
and metadata).

Authorization requests use four parts (PARC):

| Part | In this workshop |
|------|------------------|
| **Principal** | The original Linux user (`alice` or `bob`), not root |
| **Action** | A named capability, e.g. `ReadLogs` or `Restart` |
| **Resource** | Usually `Linux::Service::"cedar-demo"` |
| **Context** | Session facts, especially `local_console` (local vs SSH) |

Cedar is **default-deny**. A matching `forbid` always wins over a `permit`.

### 4. Know the two demo users

| User | Groups | Starter intent |
|------|--------|----------------|
| **alice** | `developers` | May read demo logs; may **not** restart yet |
| **bob** | `operators` | May read logs and restart the demo service **from the local console** |

You will start class logged in as **alice**.

If the prepared image does not already include these accounts, create them with home directories and the groups the starter policies check:

```bash
sudo groupadd developers
sudo groupadd operators
sudo useradd -m -G developers alice
sudo useradd -m -G operators bob
```

### 5. Optional: open this README offline

Clone or copy this repo so you can read these steps without relying on Wi‑Fi
during the session.

---

## When you arrive

1. Start the workshop VM and log in as **alice**.
2. Open a terminal.
3. Confirm identity and the demo service:

```bash
id
systemctl status cedar-demo --no-pager
```

You should see yourself as `alice` in the `developers` group, and
`cedar-demo.service` active.

4. Open a second tab or window for this README so you can copy commands.
5. Wait for the facilitator intro (next section). Do not race ahead into policy
   edits until the room is on that phase—timing is tight.

If something is broken before class starts, tell a facilitator. On a prepared
VM you can also try:

```bash
sudo /opt/cedudo/reset-workshop
```

---

## Class — follow along (80 minutes)

### Minutes 0–8 — Why this architecture

Ordinary `sudoers` rules grow into “alice may run this command, bob may run that
one, only on this host, with these arguments…”. The workshop shows a cleaner

```text
                    Same cedudo.cjar
                     /             \
                    v               v
Browser + Tarp                  Local VM
Cedarling WASM                  cedudo restart-demo
Policy testing                         |
                                       v
                               Cedarling Python
                                       |
                               Permit or Deny
                                       |
                              Fixed root command
```

Cedar decides whether a **capability** is allowed. A root-owned manifest
(`operations.json`) binds that capability to one exact executable and argument
list. You never pass shell command strings to `cedudo`.

---

### Minutes 8–18 — Inspect the VM

Still as **alice**, run:

```bash
id
systemctl status cedar-demo --no-pager
cedudo view-logs
cedudo restart-demo
```

Expected with the starter policies:

| Command | Result |
|---------|--------|
| `cedudo view-logs` | **PERMIT** — alice is in `developers` |
| `cedudo restart-demo` | **DENY** — alice is not in `operators` |

Confirm that direct admin commands cannot be run:

```bash
systemctl restart cedar-demo
```

That should be **denied** because you don't have root privileges. Only `cedudo` can elevate via setuid.

If the facilitator asks you to try **bob** (local console session):

```bash
su - bob
# or: ssh bob@localhost   (then local_console may be false — see later)
cedudo restart-demo
```

As bob on a **local** console, restart should **PERMIT**. Switch back to alice
when asked.

---

### Minutes 18–32 — Reproduce the decision in Tarp

Start the local policy HTTP server (CORS enabled for Tarp):

```bash
cd ~/cedudo-workshop/policy
# If your materials live in this repo instead:
# cd /path/to/cedudo/policy
python3 ../tools/serve-policy.py
```

Leave that terminal running. In Tarp:

1. Set the policy store URL to `http://127.0.0.1:8000/cedudo.cjar`
2. Use **unsigned** authorization (you supply the principal; no OIDC needed)
3. Load the example request JSON files from `examples/` (or
   `~/cedudo-workshop/examples/`)

Work through these scenarios and note permit vs deny:

| Example file | Expected |
|--------------|----------|
| `alice-read-logs.json` | PERMIT |
| `alice-restart.json` | DENY |
| `bob-restart.json` (`local_console: true`) | PERMIT |
| `bob-restart-remote.json` (`local_console: false`) | DENY |
| `root-shell.json` (`OpenShell`) | DENY (forbid policy) |

You are learning PARC without standing up an identity provider.

---

### Minutes 32–45 — Modify the policies

Open the starter policies under `policy/store/policies/` (or
`~/cedudo-workshop/policy/store/policies/`). You will see:

- Developers/operators may `ReadLogs` on `cedar-demo`
- Operators may `Restart` on `cedar-demo` when `context.local_console` is true
- Everyone is forbidden from `OpenShell`

**Challenge:** Permit members of `developers` to restart the demo service, but
only when the resource is noncritical and the request is from the local console.

Create a new file, for example
`policy/store/policies/developers-restart-noncritical-local.cedar`:

```cedar
@id("developers-restart-noncritical-local")
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

Rebuild the shared archive:

```bash
cd ~/cedudo-workshop   # or the repo root
./tools/build-cjar.sh
```

Reload the policy store in Tarp (or refresh), then rerun `alice-restart.json`.
It should now **PERMIT**.

---

### Minutes 45–58 — Deploy the same policy to the VM

When Tarp looks right, install the archive for enforcement (requires root privileges):

```bash
sudo ./tools/deploy-policy.sh
```

That validates `policy/cedudo.cjar`, copies it to `/opt/cedudo/cedudo.cjar`, and
sets root ownership with mode `0644`.

Note: The deploy script still uses `sudo` for administrative tasks like copying files to `/opt/cedudo/`. The `cedudo` replacement only applies to the privilege wrapper itself.

As **alice** on a local console:

```bash
cedudo restart-demo
systemctl status cedar-demo --no-pager
```

Alice should now receive **PERMIT**, and `cedar-demo` should restart. This is
the central moment of the workshop: the policy you tested in the browser now
controls a real privileged operation.

---

### Minutes 58–70 — Attack the design

Try to break out. Every attempt below should **fail**:

```bash
cedudo ../../bin/bash
cedudo "restart-demo; /bin/bash"
cedudo restart-demo --service ssh
cedudo root-shell
systemctl restart cedar-demo
```

Why they fail:

- `cedudo` accepts only a kebab-case **operation ID**, not a command path
- Trailing arguments (like `--service ssh`) are ignored; argv comes from the
  root-owned manifest
- `root-shell` is not in `operations.json` (rejected before Cedar runs)
- `systemctl` runs without root privileges since cedudo is the only setuid executable
- You cannot rewrite `/opt/cedudo/operations.json` or `cedudo.cjar` without root access

A Cedar **permit** never lets the caller change which binary runs.

---

### Minutes 70–77 — Add one contextual control

Pick **one** extra rule, add it under `policy/store/policies/`, rebuild, retest
in Tarp, and redeploy if you have time.

**Option A — forbid remote restarts**

```cedar
@id("forbid-remote-restart")
forbid (
    principal,
    action == Linux::Action::"Restart",
    resource
)
when {
    !context.local_console
};
```

**Option B — require two groups**

```cedar
@id("operators-oncall-restart")
permit (
    principal,
    action == Linux::Action::"Restart",
    resource == Linux::Service::"cedar-demo"
)
when {
    principal.groups.contains("operators") &&
    principal.groups.contains("oncall") &&
    context.local_console
};
```

Rebuild and redeploy the same way as before:

```bash
./tools/build-cjar.sh
# retest in Tarp
sudo ./tools/deploy-policy.sh  # Still needs sudo for copying to /opt/cedudo/
```

---

### Minutes 77–80 — Debrief

Map what you used:

```text
Linux identity        → Principal
Privileged capability → Action
Service / host        → Resource
Session conditions    → Context
Cedarling             → Decision
cedudo (setuid)       → Enforcement + Privilege transition
```

What this workshop deliberately left out (and what production would need):

- JWT / OIDC or workload identity instead of application-asserted principals
- Signed, versioned policy stores with rollback protection
- A compiled root-owned enforcement binary (not a Python script)
- Secure decision logging and stronger environment sanitization
- Formal review of every operation-to-`argv` binding
- Installing Janssen Server or a full identity stack

Unsigned authorization is fine for local learning. It is not enough for a real
privilege path.

---

## If something goes wrong

| Symptom | What to check |
|---------|----------------|
| Tarp will not load policies | Is `python3 ../tools/serve-policy.py` still running? URL exactly `http://127.0.0.1:8000/cedudo.cjar`? |
| CORS errors in the browser | Use the provided `serve-policy.py` (it sends CORS headers) |
| `Cedarling initialization failed` | `/opt/cedudo/cedudo.cjar` exists, owned by root, not group/world writable; `metadata.json` uses `cedar_version` (not `policy_engine`) |
| `unknown operation` | Only IDs in `operations.json` are valid (`view-logs`, `status-demo`, `restart-demo`) |
| `operation must match [a-z]…` | Operation IDs are kebab-case only—no paths or shell metacharacters |
| `must be installed as setuid root` | The C wrapper `/opt/cedudo/cedudo` must have setuid bit. Run: `sudo chmod 4755 /opt/cedudo/cedudo` |
| Permission denied when running cedudo | The wrapper binary must be executable and have setuid bit. See INSTALL.md for C wrapper setup |
| Policies changed but VM behavior did not | Rebuild with `./tools/build-cjar.sh`, then deploy with root privileges |

Reset the VM to the starter state:

```bash
sudo /opt/cedudo/reset-workshop
```

---

## After class (optional reading)

Repository layout if you want to explore later:

```text
cedudo.py                 Python enforcement script
cedudo-wrapper.c          C wrapper for setuid support
install-wrapper.sh        Script to build and install the wrapper
operations.json           Operation ID → fixed argv
policy/store/             Cedarling policy store (edit here)
policy/cedudo.cjar        Packaged store (ZIP)
examples/                 Tarp unsigned request samples
tools/build-cjar.sh       Package store → .cjar
tools/serve-policy.py     Local CORS server for Tarp
tools/deploy-policy.sh    Install .cjar to /opt/cedudo/
```

Design notes and requirements for facilitators live under
[`.kiro/specs/cedar-sudo-workshop/`](.kiro/specs/cedar-sudo-workshop/).


## Why a C Wrapper?



### The Setuid-on-Scripts Problem

Modern Linux kernels **ignore the setuid bit on interpreted scripts** (files beginning with `#!`) for security reasons. This is by design - see the Linux kernel documentation on script execution.

When you set the setuid bit on `cedudo.py`:

- The bit is stored in the filesystem
- But the kernel ignores it when executing the script
- The Python interpreter runs with the **user's privileges**, not root



### The Solution

The C wrapper (`cedudo-wrapper.c`) is a compiled binary that:

1. **Can use setuid** (compiled binaries are allowed)
2. Executes the Python interpreter with the script path
3. The Python process inherits the elevated privileges
4. `cedudo.py` can then use `os.getuid()` (real UID) and `os.geteuid()` (effective UID = 0)

This is the same approach used by many setuid wrappers in production systems.

## Security Notes



### Setuid Root

The `cedudo.py` script must be installed with the setuid bit (mode 4755) so it runs with root privileges when invoked by regular users. This is controlled and safe because:

1. The script only accepts operation IDs (kebab-case identifiers), not commands
2. All commands and arguments come from a root-owned manifest (`operations.json`)
3. Authorization is evaluated by Cedarling using Cedar policies
4. The script fails closed on any error
5. The environment is sanitized before executing privileged commands



### File Security Requirements

All files in `/opt/cedudo/` must be:

- Owned by root (UID 0)
- Not group-writable or world-writable
- Regular files (not symlinks)

The script validates these requirements at runtime and refuses to execute if they're not met.

### How it works

`cedudo` uses the setuid mechanism for privilege elevation:

- **Direct invocation**: Users run `cedudo` directly (no sudo wrapper)
- **Cedar-based access control**: All authorization decisions come from Cedar policies
- **Simple privilege model**: One setuid executable that handles elevation and enforcement
- **Fail-safe design**: Authorization, manifest validation, and secure command execution



### What sudo is still needed for

Administrative tasks like:

- Deploying policy updates (`sudo ./tools/deploy-policy.sh`)
- Installing the system (`sudo` commands in this guide)
- Resetting workshop state (`sudo /opt/cedudo/reset-workshop`)

These tasks modify root-owned system files and are outside cedudo's operation.
