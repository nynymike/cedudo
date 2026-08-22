# Installing cedudo

This document describes how to install `cedudo` as a setuid-root executable.

## Quick Fix: "must be installed as setuid root" Error

If you're seeing this error, the setuid bit is not set. Run:

```bash
sudo chown root:root /opt/cedudo/cedudo.py
sudo chmod 4755 /opt/cedudo/cedudo.py
ls -l /opt/cedudo/cedudo.py  # Should show: -rwsr-xr-x (note the 's')
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

```bash
# Set root ownership
sudo chown root:root \
    /opt/cedudo/cedudo.py \
    /opt/cedudo/operations.json \
    /opt/cedudo/cedudo.cjar

# Set setuid on the main executable
sudo chmod 4755 /opt/cedudo/cedudo.py

# Make config files read-only
sudo chmod 0644 /opt/cedudo/operations.json
sudo chmod 0644 /opt/cedudo/cedudo.cjar
```

### 5. Create a convenient symlink (optional)

```bash
sudo ln -sf /opt/cedudo/cedudo.py /usr/local/bin/cedudo
```

After this, users can run:

```bash
cedudo view-logs
# or
cedudo view-logs  # if symlink was created
```

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
# Check permissions
ls -l /opt/cedudo/

# Should show:
# -rwsr-xr-x root root cedudo.py    ← Note the 's' in 'rws' (setuid bit)
# -rw-r--r-- root root operations.json
# -rw-r--r-- root root cedudo.cjar

# Verify the setuid bit is set (should output '4755')
stat -c '%a' /opt/cedudo/cedudo.py

# Verify ownership is root (should output '0')
stat -c '%u' /opt/cedudo/cedudo.py

# Test as a regular user (switch to alice or another non-root user)
cedudo view-logs
```

**What to look for:**
- The **`s`** in `-rwsr-xr-x` means the setuid bit is set
- Permissions `4755` where the `4` prefix indicates setuid
- Owner must be `root` (UID 0)
- If you see `-rwxr-xr-x` instead of `-rwsr-xr-x`, the setuid bit is missing

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `must be installed as setuid root` | The setuid bit is missing. Run: `sudo chown root:root /opt/cedudo/cedudo.py && sudo chmod 4755 /opt/cedudo/cedudo.py` |
| `cannot inspect policy store` | Verify files are owned by root and in `/opt/cedudo/` |
| `Cedarling initialization failed` | Check that `cedudo.cjar` exists and is valid |
| `invoking user not found` | Ensure your user account exists in `/etc/passwd` |
| Permission denied | The script must be executable with setuid bit set |
| Script works for root but not regular users | Check that the setuid bit is set with `ls -l /opt/cedudo/cedudo.py` (should show `s` in permissions) |

### Common Cause: Setuid Bit Lost

The setuid bit can be lost when:
- Copying files without preserving permissions (`cp` without `-p`)
- Extracting from archives that don't preserve special bits
- Editing the file with some editors
- File system mounted with `nosuid` option

**Always re-run the permission commands after copying or modifying the file:**
```bash
sudo chown root:root /opt/cedudo/cedudo.py
sudo chmod 4755 /opt/cedudo/cedudo.py
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
