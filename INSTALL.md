# Installing cedudo

This document describes how to install `cedudo` as a setuid-root executable.

## Prerequisites

- A Linux system (tested on Ubuntu/Debian)
- Python 3.8 or later, including `venv` and `pip`
- Git
- GCC (to compile the C wrapper)
- `cedarling_python` (the Janssen Cedarling Python bindings)
- Root access for installation
- On Ubuntu/Debian, install the build and Python tools with:

```bash
sudo apt update
sudo apt install gcc python3 python3-venv python3-pip
```

## Installation Steps

### 1. Clone the repository

```bash
git clone https://github.com/nynymike/cedudo.git
cd cedudo
```

Later steps assume you are in this clone.

### 2. Create the installation directory

```bash
sudo mkdir -p /opt/cedudo
```



### 3. Set up the Python virtual environment and install `cedarling_python`

`cedudo.py` imports `cedarling_python`. Install that module into the
`/opt/cedudo/venv` interpreter the C wrapper uses. The PyPI package name is
`cedarling-python`; the import name is `cedarling_python`.

```bash
sudo python3 -m venv /opt/cedudo/venv
sudo /opt/cedudo/venv/bin/pip install --upgrade pip
sudo /opt/cedudo/venv/bin/pip install cedarling-python
```

Confirm the module is available (this must succeed before you continue):

```bash
sudo /opt/cedudo/venv/bin/python3 -c "import cedarling_python; print('cedarling_python OK')"
```

If that command raises `ModuleNotFoundError: No module named 'cedarling_python'`,
the package is not installed in this venv. Re-run the `pip install` above and
do not run `cedudo.py` with system `python3`.

### 4. Copy the files

```bash
sudo cp cedudo.py /opt/cedudo/cedudo.py
sudo cp operations.json /opt/cedudo/operations.json
sudo cp policy/cedudo.cjar /opt/cedudo/cedudo.cjar
```



### 5. Set ownership and permissions

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



### 6. Create a convenient symlink

The `install-wrapper.sh` script already creates this, but if needed:

```bash
sudo ln -sf /opt/cedudo/cedudo /usr/local/bin/cedudo
```

After this, users can run:

```bash
cedudo view-logs
cedudo restart-demo
```

### 7. Create the demo users

The starter policies authorize by Linux group. Create `alice` in `developers` and `bob` in `operators`, each with a home directory:

```bash
sudo groupadd developers
sudo groupadd operators
sudo useradd -m -G developers alice
sudo useradd -m -G operators bob
```

| User | Groups | Starter intent |
|------|--------|----------------|
| **alice** | `developers` | May read demo logs; may **not** restart yet |
| **bob** | `operators` | May read logs and restart the demo service from the local console |

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

- The `s` in `-rwsr-xr-x` on the **cedudo binary** (not cedudo.py)
- Permissions `4755` where the `4` prefix indicates setuid
- Owner must be `root` (UID 0)
- If you see `-rwxr-xr-x` instead of `-rwsr-xr-x`, the setuid bit is missing

**Common mistake:** Setting setuid on `cedudo.py` instead of the compiled `cedudo` wrapper. The wrapper must have the setuid bit, not the Python script.

## Troubleshooting


| Issue                                                     | Solution                                                                                                                                        |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'cedarling_python'` | Install into the venv the wrapper uses: `sudo /opt/cedudo/venv/bin/pip install cedarling-python`. Do not run `cedudo.py` with system `python3`. |
| `must be installed as setuid root`                        | Most likely: setuid doesn't work on Python scripts. Use the C wrapper: `./install-wrapper.sh`                                                   |
| Wrapper not found                                         | Compile it: `gcc -o cedudo cedudo-wrapper.c && sudo cp cedudo /opt/cedudo/cedudo && sudo chmod 4755 /opt/cedudo/cedudo`                         |
| `cannot inspect policy store`                             | Verify files are owned by root and in `/opt/cedudo/`                                                                                            |
| `Cedarling initialization failed`                         | Check that `cedudo.cjar` exists and is valid. `metadata.json` must use `cedar_version` (see Cedarling policy store format).                     |
| `invoking user not found`                                 | Ensure your user account exists in `/etc/passwd`                                                                                                |
| Permission denied                                         | The **wrapper binary** must be executable with setuid bit set                                                                                   |
| Script works for root but not regular users               | Check that `/opt/cedudo/cedudo` (not cedudo.py) has the setuid bit: `ls -l /opt/cedudo/cedudo`                                                  |




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