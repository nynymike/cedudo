# Installing cedudo

This document describes how to install `cedudo` as a setuid-root executable.

## Quick Fix: "must be installed as setuid root" Error

**If you're seeing this error with correct permissions on cedudo.py:**

Modern Linux systems don't allow setuid on interpreted scripts (files with `#!/usr/bin/python3` shebangs). You need to use the **C wrapper** instead:

```bash
# Install the compiled wrapper
chmod +x install-wrapper.sh
./install-wrapper.sh
```

This creates `/opt/cedudo/cedudo` (a compiled binary) that can use setuid and executes the Python script.

**If the wrapper is already installed but still not working:**

```bash
sudo chown root:root /opt/cedudo/cedudo
sudo chmod 4755 /opt/cedudo/cedudo
ls -l /opt/cedudo/cedudo  # Should show: -rwsr-xr-x (note the 's')
```

For full installation instructions, continue reading below.

## Prerequisites

- Python 3.8 or later
- Root access for installation
- A Linux system (tested on Ubuntu/Debian)

## Installation Steps

### 1. Create the installation directory

```bash
sudo mkdir -p /opt/cedudo
```

### 2. Set up the Python virtual environment

```bash
sudo python3 -m venv /opt/cedudo/venv
sudo /opt/cedudo/venv/bin/pip install cedarling-python
```

### 3. Copy the files

```bash
sudo cp cedudo.py /opt/cedudo/cedudo.py
sudo cp operations.json /opt/cedudo/operations.json
sudo cp policy/cedudo.cjar /opt/cedudo/cedudo.cjar
```

### 4. Set ownership and permissions

**Important:** Most modern Linux systems don't allow setuid on interpreted scripts. You must use the compiled C wrapper:

```bash
# Compile and install the wrapper
chmod +x install-wrapper.sh
./install-wrapper.sh
```

This creates `/opt/cedudo/cedudo` (a compiled binary with setuid) that executes the Python script.

**Alternative (if wrapper is already installed):**

```bash
# Set root ownership
sudo chown root:root \
    /opt/cedudo/cedudo \
    /opt/cedudo/cedudo.py \
    /opt/cedudo/operations.json \
    /opt/cedudo/cedudo.cjar

# Set setuid on the wrapper binary
sudo chmod 4755 /opt/cedudo/cedudo

# Make config files and script read-only
sudo chmod 0644 /opt/cedudo/cedudo.py
sudo chmod 0644 /opt/cedudo/operations.json
sudo chmod 0644 /opt/cedudo/cedudo.cjar
```

### 5. Create a convenient symlink

The `install-wrapper.sh` script already creates this, but if needed:

```bash
sudo ln -sf /opt/cedudo/cedudo /usr/local/bin/cedudo
```

After this, users can run:

```bash
cedudo view-logs
cedudo restart-demo
```

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

## Verification

After installation, verify the setup:

```bash
# Check the wrapper binary has setuid
ls -l /opt/cedudo/cedudo

# Should show:
# -rwsr-xr-x root root cedudo    ← This is the compiled wrapper with setuid bit
```

```bash
# Check other files
ls -l /opt/cedudo/

# Should show:
# -rwsr-xr-x root root cedudo              ← Compiled wrapper (setuid)
# -rw-r--r-- root root cedudo.py           ← Python script (no setuid needed)
# -rw-r--r-- root root operations.json
# -rw-r--r-- root root cedudo.cjar

# Verify the setuid bit is set (should output '4755')
stat -c '%a' /opt/cedudo/cedudo

# Verify ownership is root (should output '0')
stat -c '%u' /opt/cedudo/cedudo

# Test as a regular user (switch to alice or another non-root user)
su - alice
cedudo view-logs
```

**What to look for:**
- The **`s`** in `-rwsr-xr-x` on the **cedudo binary** (not cedudo.py)
- Permissions `4755` where the `4` prefix indicates setuid
- Owner must be `root` (UID 0)
- If you see `-rwxr-xr-x` instead of `-rwsr-xr-x`, the setuid bit is missing

**Common mistake:** Setting setuid on `cedudo.py` instead of the compiled `cedudo` wrapper. The wrapper must have the setuid bit, not the Python script.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `must be installed as setuid root` | Most likely: setuid doesn't work on Python scripts. Use the C wrapper: `./install-wrapper.sh` |
| Wrapper not found | Compile it: `gcc -o cedudo cedudo-wrapper.c && sudo cp cedudo /opt/cedudo/cedudo && sudo chmod 4755 /opt/cedudo/cedudo` |
| `cannot inspect policy store` | Verify files are owned by root and in `/opt/cedudo/` |
| `Cedarling initialization failed` | Check that `cedudo.cjar` exists and is valid |
| `invoking user not found` | Ensure your user account exists in `/etc/passwd` |
| Permission denied | The **wrapper binary** must be executable with setuid bit set |
| Script works for root but not regular users | Check that `/opt/cedudo/cedudo` (not cedudo.py) has the setuid bit: `ls -l /opt/cedudo/cedudo` |

### Common Issue: Setuid on Scripts

**Symptom:** Permissions look correct (`-rwsr-xr-x` on `cedudo.py`) but still get "must be installed as setuid root"

**Cause:** Modern Linux kernels ignore the setuid bit on interpreted scripts for security reasons.

**Solution:** Use the compiled C wrapper:
```bash
./install-wrapper.sh
```

The wrapper is a compiled binary that CAN use setuid, and it executes the Python script with elevated privileges.

### Common Cause: Setuid Bit Lost

The setuid bit can be lost when:
- Copying files without preserving permissions (`cp` without `-p`)
- Extracting from archives that don't preserve special bits
- Editing the file with some editors
- File system mounted with `nosuid` option

**Always re-run the permission commands after copying or modifying the wrapper:**
```bash
sudo chown root:root /opt/cedudo/cedudo
sudo chmod 4755 /opt/cedudo/cedudo
```

## Uninstallation

```bash
sudo rm -rf /opt/cedudo
sudo rm -f /usr/local/bin/cedudo
```

## Workshop Reset

For workshop environments, you may want to provide a reset script:

```bash
sudo /opt/cedudo/reset-workshop
```

This should restore the original policies and service state.
