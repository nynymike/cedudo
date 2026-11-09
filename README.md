# Overview

`cedudo` is a more restrictive alternative to the `sudo` command where Cedar policies
are used to control access to what linux commands a user can run. Cedudo looks up
the Linux groups of the user and maps other information into the context, e.g. time of 
day. Cedudo is very restrictive by design, and is meant for demo purposes. 

# Installing cedudo

This document describes how to install `cedudo` as a setuid-root executable.

## Prerequisites

- **Supported workshop environment: Ubuntu 24.04 LTS with systemd running,
  using its system Python 3 (3.12).** The complete workshop installation
  (Cedudo plus the `cedar-demo` service) is supported and tested only there.
- Python 3 with `venv` and `pip` (the Ubuntu 24.04 packages below)
- Git
- GCC (to compile the C wrapper)
- `cedarling_python` (the Janssen Cedarling Python bindings)
- Root access for installation
- On Ubuntu 24.04, install the build and Python tools with:

```bash
apt update
apt install gcc python3 python3-venv python3-pip git
```

### Environment support

| Component | Requirement |
| --- | --- |
| Complete workshop (Cedudo + `cedar-demo.service`, exercises) | Ubuntu 24.04 with systemd running, system Python. `tools/install-demo-service.sh` refuses to run anywhere else. |
| `cedudo.py` alone | Linux with a compiler, Python 3.9 or later (it imports `zoneinfo`, which Python 3.8 lacks) and a `cedarling-python` build for your platform. Not tested outside Ubuntu 24.04. |
| `tools/cedudo-simulate.py`, `tests/` | Python 3.9 or later, any OS. No root or systemd. |

An ordinary container (for example a default Docker image) does **not** meet
the installer's requirements: it normally has no systemd running, so the
`cedar-demo` service cannot be installed, started, or restarted. Use an Ubuntu
24.04 VM.

## Installation Steps

### 1. Clone the repository

```bash
git clone https://github.com/nynymike/cedudo.git
cd cedudo
```

Later steps assume you are in this clone.

### 2. Create the installation directory

```bash
mkdir -p /opt/cedudo
```



### 3. Set up the Python virtual environment and install `cedarling_python`

`cedudo.py` imports `cedarling_python`. Install that module into the
`/opt/cedudo/venv` interpreter the C wrapper uses. The PyPI package name is
`cedarling-python`; the import name is `cedarling_python`.

```bash
python3 -m venv /opt/cedudo/venv
/opt/cedudo/venv/bin/pip install --upgrade pip
/opt/cedudo/venv/bin/pip install cedarling-python
```

Confirm the module is available (this must succeed before you continue):

```bash
/opt/cedudo/venv/bin/python3 -c "import cedarling_python; print('cedarling_python OK')"
```

If that command raises `ModuleNotFoundError: No module named 'cedarling_python'`,
the package is not installed in this venv. Re-run the `pip install` above and
do not run `cedudo.py` with system `python3`.

### 4. Copy the files

```bash
cp cedudo.py /opt/cedudo/cedudo.py
cp operations.json /opt/cedudo/operations.json
cp policy/cedudo.cjar /opt/cedudo/cedudo.cjar
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
groupadd developers
groupadd operators
useradd -m -s /bin/bash -G developers alice
useradd -m -s /bin/bash -G operators bob
```


| User      | Groups       | Starter intent                                                    |
| --------- | ------------ | ----------------------------------------------------------------- |
| **alice** | `developers` | May observe the demo (`read-logs`); may **not** restart |
| **bob**   | `operators`  | May observe the demo and restart **noncritical** services when `intruder_risk_level` is `low` |


### 7. Install the demo service (administrator)

`read-logs` and `restart-demo` act on a real, harmless systemd service,
`cedar-demo.service`. Installing, validating, and removing it are administrator
tasks documented separately in [`docs/demo-service.md`](docs/demo-service.md).
In short, on the Ubuntu 24.04 VM:

```bash
sudo tools/install-demo-service.sh
sudo install -o root -g root -m 0644 operations.json /opt/cedudo/operations.json
```

Students never run these.

Operations in `operations.json`:

| Operation | Cedar action / resource | Execution |
| --- | --- | --- |
| `read-logs` | `read-logs` on `Linux::Service::"cedar-demo"` | **Real**: `/usr/bin/journalctl --unit=cedar-demo.service --lines=20 --no-pager --output=short-iso` |
| `restart-demo` | `restart` on `Linux::Service::"cedar-demo"` | **Real**: `/usr/bin/systemctl --no-ask-password --no-pager restart cedar-demo.service` |
| `restart-ssh` | `restart` on `Linux::Service::"ssh"` (critical) | **Simulated**: prints a message; SSH is never restarted |

The caller supplies only the operation ID; extra arguments are logged and
ignored.

### 8. Testing

After installation, verify the setup by logging in as different Linux users and trying to run cedudo to do different things.

**Business hours:** the deployed `forbid-restart-outside-hours` policy denies
every `restart` request when the `America/Chicago` hour is before 09:00 or at or
after 17:00 (any day). `cedudo` reads the server clock; callers cannot override
it. Run restart tests inside that window, or have the administrator set the VM
clock (see `workshop-overview.md`). Outputs below assume the window.

#### Test as alice

To run this command you must be root. It will log you in as alice. 
```bash
su - alice
```

```bash
cedudo read-logs
```


>cedudo[4669]: INFO PERMIT user=alice uid=1000 groups=['alice', 'developers'] operation=read-logs action=Linux::Action::"read-logs" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['developers-observe-demo'] exec=['/usr/bin/journalctl', '--unit=cedar-demo.service', '--lines=20', '--no-pager', '--output=short-iso']
>(up to 20 recent `cedar-demo` journal entries)

```bash
cedudo restart-demo
```


>cedudo[4702]: WARNING DENY user=alice uid=1000 groups=['alice', 'developers'] operation=restart-demo action=Linux::Action::"restart" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=[]
>cedudo: denied: restart-demo

```bash
cedudo restart-ssh
```

>cedudo[4708]: WARNING DENY user=alice uid=1000 groups=['alice', 'developers'] operation=restart-ssh action=Linux::Action::"restart" resource=Linux::Service::"ssh" local_console=False interactive=True intruder_risk_level=low policies=['forbid-critical-restart']

#### Test as `bob`

Now let's try as `bob`. Remember to exit the shell of `alice` so you are root again.

```bash
su - bob
```

```bash
cedudo read-logs
```
>cedudo[4686]: INFO PERMIT user=bob uid=1001 groups=['bob', 'operators'] operation=read-logs action=Linux::Action::"read-logs" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['developers-observe-demo'] exec=['/usr/bin/journalctl', '--unit=cedar-demo.service', '--lines=20', '--no-pager', '--output=short-iso']

>(up to 20 recent `cedar-demo` journal entries)

```bash
cedudo restart-demo
```

> cedudo[4729]: INFO PERMIT user=bob uid=1001 groups=['bob', 'operators'] operation=restart-demo action=Linux::Action::"restart" resource=Linux::Service::"cedar-demo" local_console=False interactive=True intruder_risk_level=low policies=['operators-restart'] exec=['/usr/bin/systemctl', '--no-ask-password', '--no-pager', 'restart', 'cedar-demo.service']

>(no output; confirm with `systemctl show cedar-demo.service -p InvocationID`, which changes after the restart)

```bash
cedudo restart-ssh
```

>cedudo[4735]: WARNING DENY user=bob uid=1001 groups=['bob', 'operators'] operation=restart-ssh action=Linux::Action::"restart" resource=Linux::Service::"ssh" local_console=False interactive=True intruder_risk_level=low policies=['forbid-critical-restart']

>cedudo: denied: restart-ssh

# Configuring Ubuntu OIDC Login with authd

Configure SSH keyboard-interactive authentication to log in through an OIDC provider using OAuth Device Flow.

## 1. Install packages

Use Ubuntu **24.04** or later. Run the server commands as root.

```bash
apt update
apt install software-properties-common
```

```bash
# Ubuntu 24.04 only
add-apt-repository ppa:ubuntu-enterprise-desktop/authd
```

```bash
apt install authd snapd
```

```bash
snap install authd-oidc
```

## 2. Prepare the OAuth Client to the IdP

How you add a client and the exact config will depend on your IDP. Here is a client config from Janssen Auth Server
which covers the important points: 

```
redirectUris: ["https://localhost"]
grantTypes: ["urn:ietf:params:oauth:grant-type:device_code", "authorization_code", "refresh_token"]
scopes: ["profile", "role", "offline_access", "openid", "email"]
tokenEndpointAuthMethod: "client_secret_post"
responseTypes: ["code"]
applicationType: "native"
clientName: "My Ubuntu Linux Server"
description: "Linux authd login Service"
displayName: "My Ubuntu Linux Server"
subjectType: "pairwise"
```

3. Add a User to the IDP. 

Add the following claims for the User: 

* Username
* First Name
* Last Name
* Display Name
* Email 
* Active - `true`
* Email Verified - `true` 

## 3. Register the OIDC broker

Copy the supplied broker registration file:

```bash
cp /snap/authd-oidc/current/conf/authd/oidc.conf \
  /etc/authd/brokers.d/oidc.conf

chmod 644 /etc/authd/brokers.d/oidc.conf
```

Leave the supplied `[authd]` contents intact. This file tells authd how to communicate with the broker; it does not contain the IdP connection settings.

## 4. Enable SSH keyboard-interactive authentication

Keep your current administrator session open while configuring and testing.

Create an early-loading SSH configuration file:

```bash
cat > /etc/ssh/sshd_config.d/00-authd.conf <<'EOF'
UsePAM yes
KbdInteractiveAuthentication yes
EOF
```

Validate and reload:

```bash
sshd -t && systemctl reload ssh
```

Check the effective settings:

```bash
sshd -T | grep -E \
  '^(usepam|kbdinteractiveauthentication|authenticationmethods) '
```

For this setup, expect:

```text
usepam yes
kbdinteractiveauthentication yes
authenticationmethods any
```

If the settings differ, inspect conflicting configuration:

```bash
grep -RniE '^[[:space:]]*(Include|Match|UsePAM|KbdInteractiveAuthentication|ChallengeResponseAuthentication|AuthenticationMethods)' \
  /etc/ssh/sshd_config /etc/ssh/sshd_config.d/
```

OpenSSH generally uses the first obtained value for each setting. An earlier directive or a relevant `Match` block may affect the result. Resolve the conflict and repeat validation before testing.

Enabling keyboard-interactive authentication also permits other authentication methods configured in the PAM stack, including local Unix passwords.

## 5. Configure the IdP connection

Edit:

```bash
nano /var/snap/authd-oidc/current/broker.conf
```

Update the existing sections rather than adding duplicate sections:

```ini
[oidc]
issuer = <ISSUER_URL>
client_id = <YOUR_CLIENT_ID>
client_secret = <YOUR_CLIENT_SECRET>
extra_scopes = offline_access,email,role,profile,openid

[users]
home_base_dir = /home
ssh_allowed_suffixes_first_auth = @gluu.info,@gluu.org
extra_groups = federated
```

* *Replace the issuer and client credentials with your actual values.*

* The suffix in `ssh_allowed_suffixes_first_auth` applies to the SSH username, such as `alice@gluu.info`. It is not the Ubuntu server’s domain or the IdP hostname.


## 6. Restart and verify authd

```bash
snap restart authd-oidc
systemctl restart authd

systemctl status authd --no-pager
snap services authd-oidc
```

Check that PAM and user lookup include authd:

```bash
grep -n authd /etc/pam.d/common-auth
grep '^passwd:' /etc/nsswitch.conf
```

The first command should show an authd PAM module, such as:

```text
pam_authd_exec.so /usr/libexec/authd-pam
```

The `passwd:` entry should include `authd`, for example:

```text
passwd:         files systemd authd
```

These integrations should be configured by package installation. If they are missing, investigate the package installation before manually editing PAM.

## 7. Verify OIDC discovery

Substitute the exact configured issuer:

```bash
ISSUER='https://idp.example.org'

curl --fail --show-error \
  "${ISSUER%/}/.well-known/openid-configuration"
```

* *Replace the issuer*

Expect a JSON discovery document containing endpoints such as:

- `issuer`
- `token_endpoint`
- `jwks_uri`
- `device_authorization_endpoint`

Resolve DNS, connectivity, or certificate errors before testing login. Do not use `curl -k` for this verification.

A successful host-side curl test does not guarantee that the snap broker has identical certificate trust; check broker logs if it still fails.

## 8. Test SSH login

From another computer, replace `SERVER_IP` with the Ubuntu server address:

```bash
ssh -o PasswordAuthentication=no \
    -o PubkeyAuthentication=no \
    -o KbdInteractiveAuthentication=yes \
    -o PreferredAuthentications=keyboard-interactive \
    -l user@domain.example SERVER_IP
```

* *Replace the user with your identifier*

When prompted:

1. Select the OIDC provider.
2. Select device-code authentication if an authentication-method menu appears.
3. Open the displayed verification URI in a browser.
4. Enter the displayed code.
5. Authenticate as Alice and approve the request.
6. Complete any local-password setup prompt.

Use the full email username. Pre-created local accounts named `alice` and `bob` are separate from the authd-managed accounts. Authd creates its user record and home directory on the first successful login.

After login, verify:

```bash
whoami
id
pwd
```

Repeat for Bob:

```bash
ssh -o PasswordAuthentication=no \
    -o PubkeyAuthentication=no \
    -o KbdInteractiveAuthentication=yes \
    -o PreferredAuthentications=keyboard-interactive \
    -l bob@gluu.info SERVER_IP
```

On subsequent logins, authd may offer a local password instead of repeating device flow. If the authd local-password prompt offers navigation, enter `r` to return to authentication-method selection and choose device-code login.

## 9. Troubleshoot

Inspect recent logs:

```bash
journalctl --since "5 minutes ago" \
  -u authd \
  -u snap.authd-oidc.authd-oidc.service \
  -u ssh \
  --no-pager -l
```

Or watch while attempting login:

```bash
journalctl -f \
  -u authd \
  -u snap.authd-oidc.authd-oidc.service \
  -u ssh
```

| Symptom | What to check |
|---|---|
| `authd.service not found` | Install the `authd` Debian package; the broker snap alone is insufficient. |
| No broker configuration found | Check `/etc/authd/brokers.d/oidc.conf`, then restart authd. |
| `Permission denied (publickey)` | Check effective SSH keyboard-interactive settings and authentication restrictions. |
| First-time user “not authorized” | Check `ssh_allowed_suffixes_first_auth` under `[users]`, broker registration, and restart both services. |
| Authenticated user denied | Check `allowed_users` and the authenticated email username. |
| Plain password prompt without provider selection | Force keyboard-interactive authentication and inspect PAM and authd logs. |
| “Error connecting to provider” | Check issuer discovery, DNS, network connectivity, TLS, and broker logs. |
| Certificate “relies on legacy Common Name” | Replace the IdP certificate with one containing the correct DNS SAN. |
| Certificate “signed by unknown authority” | Configure certificate trust for the broker or use a publicly trusted certificate. |

Do not share client secrets, access tokens, refresh tokens, or ID tokens when sharing diagnostic output.

## References

- Installation: https://ubuntu.com/docs/authd/stable-docs/howto/install-authd/
- Broker configuration: https://ubuntu.com/docs/authd/stable-docs/howto/configure-authd/
- SSH login: https://ubuntu.com/docs/authd/stable-docs/howto/login-ssh/
- User onboarding: https://ubuntu.com/docs/authd/stable-docs/howto/onboard-authd-user/


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

## Uninstallation

Remove the demo service first (administrator). It stops and disables the
service and removes only the unit, `/opt/cedar-demo`, and the `cedar-demo`
account if the installer created it. It does not touch `/opt/cedudo`, `alice`,
`bob`, or the `developers`/`operators` groups:

```bash
sudo tools/uninstall-demo-service.sh
```

Then remove Cedudo itself:

```bash
sudo rm -rf /root/cedudo
sudo rm -rf /opt/cedudo
sudo rm -f /usr/local/bin/cedudo
```