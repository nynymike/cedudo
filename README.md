# Overview

`cedudo` is a more restrictive alternative to the `sudo` command where Cedar policies
are used to control access to what linux commands a user can run. Cedudo looks up
the Linux groups of the user and maps other information into the context, e.g. time of 
day. Cedudo is very restrictive by design, and is meant for demo purposes. 

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
sudo apt install gcc python3 python3-venv python3-pip git
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



### 5. Create C wrapper

**Important:** Most modern Linux systems don't allow setuid on interpreted scripts. You must use the compiled C wrapper:

```bash
# Compile and install the wrapper
chmod +x install-wrapper.sh
./install-wrapper.sh
```

This creates `/opt/cedudo/cedudo` (a compiled binary with setuid) that executes the Python script, and also sets the correct file permissions.


Verify ownership is root 
```bash
stat -c '%u' /opt/cedudo/cedudo
```
Should output `0`


```bash
stat -c '%a' /opt/cedudo/cedudo
```

Should output `4755`


### 6. Create the demo users

The starter policies authorize by Linux group. Create `alice` in `developers` and `bob` in `operators`, each with a home directory and bash as the login shell (`useradd` otherwise defaults to `/bin/sh`):

```bash
sudo groupadd developers
sudo groupadd operators
sudo useradd -m -s /bin/bash -G developers alice
sudo useradd -m -s /bin/bash -G operators bob
```


| User      | Groups       | Starter intent                                                    |
| --------- | ------------ | ----------------------------------------------------------------- |
| **alice** | `developers` | May observe the demo (`read-logs`); may **not** restart |
| **bob**   | `operators`  | May observe the demo and restart **noncritical** services when `intruder_risk_level` is `low` |


### 7. Testing

After installation, verify the setup by logging in as different Linux users and trying to run cedudo to do different things.

#### Test as alice

To run this command you must be root. It will log you in as alice. 
```bash
su - alice
```

Alice should be able to read logs. 

```bash
cedudo read-logs
```

Expected output should PERMIT because `alice` is a developer.

```
cedudo[4669]: INFO PERMIT user=alice uid=1000 groups=['alice', 'developers'] operation=read-logs action=Linux::Action::"read-logs" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['developers-observe-demo'] exec=['/usr/bin/echo', 'Access granted to read logs']
Access granted to read logs
```

```bash
cedudo restart-demo
```

Exected output should DENY because `alice` is not an operator.

```
cedudo[4702]: WARNING DENY user=alice uid=1000 groups=['alice', 'developers'] operation=restart-demo action=Linux::Action::"restart" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=[]
cedudo: denied: restart-demo
```

```bash
cedudo restart-ssh
```

Expected output should DENY because no user can restart critical services.

```
cedudo[4708]: WARNING DENY user=alice uid=1000 groups=['alice', 'developers'] operation=restart-ssh action=Linux::Action::"restart" resource=Linux::Service::"ssh" local_console=False interactive=True intruder_risk_level=low policies=['forbid-critical-restart']
cedudo: denied: restart-ssh
```

#### Test as `bob`

Now let's try as `bob`. Remember to exit the shell of `alice` so you are root again.

```bash
su - bob
```

```bash
cedudo read-logs
```

```
cedudo[4686]: INFO PERMIT user=bob uid=1001 groups=['bob', 'operators'] operation=read-logs action=Linux::Action::"read-logs" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['developers-observe-demo'] exec=['/usr/bin/echo', 'Access granted to read logs']
Access granted to read logs
```

Expected output should PERMIT because `bob` is an Operator.

```bash
cedudo restart-demo
```

```
cedudo[4729]: INFO PERMIT user=bob uid=1001 groups=['bob', 'operators'] operation=restart-demo action=Linux::Action::"restart" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['operators-restart'] exec=['/usr/bin/echo', 'Cedar demo is restarting...']
Cedar demo is restarting...
```

Expected output should PERMIT because `bob` is an Operator.

```bash
cedudo restart-ssh
```

```
cedudo[4735]: WARNING DENY user=bob uid=1001 groups=['bob', 'operators'] operation=restart-ssh action=Linux::Action::"restart" resource=Linux::Service::"ssh" local_console=False interactive=True intruder_risk_level=low policies=['forbid-critical-restart']
cedudo: denied: restart-ssh
```

Expected output should DENY because no user can restart critical services.

## Troubleshooting


| Issue                                                     | Solution                                                                                                                                        |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `cedudo[18629]: ERROR direct root invocation is not a workshop principal` | You must `su - alice` or `su - bob` to run the demo | 
| `ModuleNotFoundError: No module named 'cedarling_python'` | Install into the venv the wrapper uses: `sudo /opt/cedudo/venv/bin/pip install cedarling-python`. Do not run `cedudo.py` with system `python3`. |
| `must be installed as setuid root`                        | Most likely: setuid doesn't work on Python scripts. Use the C wrapper: `./install-wrapper.sh`                                                   |
| Wrapper not found                                         | Compile it: `gcc -o cedudo cedudo-wrapper.c && sudo cp cedudo /opt/cedudo/cedudo && sudo chmod 4755 /opt/cedudo/cedudo`                         |
| `cannot inspect policy store`                             | Verify files are owned by root and in `/opt/cedudo/`                                                                                            |
| `Cedarling initialization failed`                         | Check that `cedudo.cjar` exists and is valid. `metadata.json` must use `cedar_version` (see Cedarling policy store format).                     |
| `invoking user not found`                                 | Ensure your user account exists in `/etc/passwd`                                                                                                |
| Permission denied                                         | The **wrapper binary** must be executable with setuid bit set                                                                                   |
| Script works for root but not regular users               | Check that `/opt/cedudo/cedudo` (not cedudo.py) has the setuid bit: `stat -c '%a' /opt/cedudo/cedudo` Should be '4755'                                                |


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