# Optional: Ubuntu OIDC login with authd

**This page is optional.** The local `alice` and `bob` exercises in the main
[README](../README.md) and in `workshop-overview.md` do not use it. Do it only
if you want people to log in to the VM through an OIDC identity provider
instead of local accounts.

Logging in through OIDC proves who someone is. It does **not** authorize any
Cedudo operation. Read "Groups and authorization" below before relying on it.

Prerequisite: the main installation is complete and its checks pass. Replace
every `<PLACEHOLDER>` with your own value.

Configure SSH keyboard-interactive authentication to log in through an OIDC provider using OAuth Device Flow.
## 1. Install packages

Use Ubuntu **24.04** or later. Run the server commands from an administrator account with `sudo` (the same convention as the main installation).

```bash
sudo apt update
sudo apt install software-properties-common
```

```bash
# Ubuntu 24.04 only
sudo add-apt-repository ppa:ubuntu-enterprise-desktop/authd
```

```bash
sudo apt install authd snapd
```

```bash
sudo snap install authd-oidc
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
sudo cp /snap/authd-oidc/current/conf/authd/oidc.conf \
  /etc/authd/brokers.d/oidc.conf

chmod 644 /etc/authd/brokers.d/oidc.conf
```

Leave the supplied `[authd]` contents intact. This file tells authd how to communicate with the broker; it does not contain the IdP connection settings.

## 4. Enable SSH keyboard-interactive authentication

Keep your current administrator session open while configuring and testing.

Create an early-loading SSH configuration file:

```bash
sudo tee /etc/ssh/sshd_config.d/00-authd.conf >/dev/null <<'EOF'
UsePAM yes
KbdInteractiveAuthentication yes
EOF
```

Validate and reload:

```bash
sudo sshd -t && sudo systemctl reload ssh
```

Check the effective settings:

```bash
sudo sshd -T | grep -E \
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
sudo grep -RniE '^[[:space:]]*(Include|Match|UsePAM|KbdInteractiveAuthentication|ChallengeResponseAuthentication|AuthenticationMethods)' \
  /etc/ssh/sshd_config /etc/ssh/sshd_config.d/
```

OpenSSH generally uses the first obtained value for each setting. An earlier directive or a relevant `Match` block may affect the result. Resolve the conflict and repeat validation before testing.

Enabling keyboard-interactive authentication also permits other authentication methods configured in the PAM stack, including local Unix passwords.

## 5. Configure the IdP connection

Edit:

```bash
sudoedit /var/snap/authd-oidc/current/broker.conf
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
ssh_allowed_suffixes_first_auth = @<IDP_USER_DOMAIN>
extra_groups = federated   # adds a local group; grants nothing in Cedar (see "Groups and authorization")
```

* *Replace the issuer and client credentials with your actual values.*

* The suffix in `ssh_allowed_suffixes_first_auth` applies to the SSH username, such as `<USERNAME>@<IDP_USER_DOMAIN>`. It is not the Ubuntu server’s domain or the IdP hostname.


## Groups and authorization

The `extra_groups = federated` line above adds the local group `federated` to
users who log in through this broker. **The starter Cedar policies do not
mention `federated`.** They authorize only the Linux groups `developers` and
`operators`, so a successful OIDC login by itself grants no Cedudo capability:
`read-logs` and `restart-demo` are denied for that user (Cedar is
default-deny).

`cedudo` builds the principal from the groups the system resolves for the
logged-in user. Before expecting anything to work, inspect what you actually
got, as that user:

```bash
id
cedudo explain read-logs
cedudo explain restart-demo
```

Then decide, deliberately, how the user should be authorized. Two options:

- **Change the policy.** Add a Cedar policy that names the group the user
  really has (for example `federated`, or a group from your IdP), scoped to the
  actions and resources you intend. Rebuild and redeploy the archive as in the
  main README. This keeps the grant visible in policy.
- **Change the group membership.** Configure authd or the IdP so the user lands
  in the existing `developers` or `operators` group. Be careful:
  `extra_groups` applies to every user who logs in through the broker, so
  putting `operators` there would let every such user satisfy the
  `operators-restart` permit.

Whichever you choose, run `cedudo explain` again as that user and confirm the
decision and determining policy IDs match your intent. Forbid policies still
win: `forbid-restart-outside-hours` and `forbid-critical-restart` apply to OIDC
users exactly as they do to `alice` and `bob`.

## 6. Restart and verify authd

```bash
sudo snap restart authd-oidc
sudo systemctl restart authd

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
    -l <USERNAME>@<IDP_USER_DOMAIN> SERVER_IP
```

* *Replace `<USERNAME>` and `<IDP_USER_DOMAIN>` with the username and suffix of your IdP test user*

When prompted:

1. Select the OIDC provider.
2. Select device-code authentication if an authentication-method menu appears.
3. Open the displayed verification URI in a browser.
4. Enter the displayed code.
5. Authenticate as your IdP test user and approve the request.
6. Complete any local-password setup prompt.

Use the full email username. The local accounts `alice` and `bob` created in the main installation are separate from authd-managed accounts and keep their local groups. Authd creates its user record and home directory on the first successful login.

After login, verify:

```bash
whoami
id
pwd
```

Repeat for a second IdP user:

```bash
ssh -o PasswordAuthentication=no \
    -o PubkeyAuthentication=no \
    -o KbdInteractiveAuthentication=yes \
    -o PreferredAuthentications=keyboard-interactive \
    -l <SECOND_USERNAME>@<IDP_USER_DOMAIN> SERVER_IP
```

On subsequent logins, authd may offer a local password instead of repeating device flow. If the authd local-password prompt offers navigation, enter `r` to return to authentication-method selection and choose device-code login.

## 9. Troubleshoot

Inspect recent logs:

```bash
sudo journalctl --since "5 minutes ago" \
  -u authd \
  -u snap.authd-oidc.authd-oidc.service \
  -u ssh \
  --no-pager -l
```

Or watch while attempting login:

```bash
sudo journalctl -f \
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
| OIDC login succeeds but `cedudo` denies everything | Expected until authorized: inspect `id` and `cedudo explain <operation-id>` as that user, then see "Groups and authorization". |
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


