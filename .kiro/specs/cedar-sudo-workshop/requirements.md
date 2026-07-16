# Requirements Document

## Introduction

This document specifies the requirements for a self-contained 80-minute hands-on workshop titled "Build a Safer sudo with Cedar" for the Texas Linux Festival. The workshop teaches attendees how to use Cedar authorization policies to control privileged Linux operations through a demonstration system that separates policy decision (Cedar/Cedarling), enforcement (cedudo helper), and privilege escalation (sudo). The workshop is educational and explicitly not production-ready.

## Glossary

- **Workshop_VM**: The prepared Ubuntu or Debian virtual machine containing all pre-installed dependencies and demonstration components
- **Cedar**: The Cedar policy language and authorization framework used for making authorization decisions
- **Cedarling**: The local Policy Decision Point that evaluates Cedar policies
- **Tarp**: The browser-based Cedar policy workbench that includes Cedarling as WASM and supports unsigned authorization testing
- **Cedudo**: The root-owned Policy Enforcement Point helper that validates operations and enforces Cedar authorization decisions
- **Demo_Service**: The harmless systemd service (cedar-demo.service) used for safe demonstration of privileged operations
- **Policy_Store**: The .cjar file containing compiled Cedar policies, schema, and entities
- **Operations_Manifest**: The root-owned operations.json file that binds operation IDs to fixed command arrays
- **Workshop_Files**: The collection of policies, examples, tools, and documentation in ~/cedudo-workshop/
- **Operation_ID**: A kebab-case identifier (e.g., "view-logs", "restart-demo") that references a fixed privileged operation
- **Principal**: The Cedar entity representing the original Linux user identity with uid, gid, and group memberships
- **Action**: The Cedar entity representing the privileged capability being requested (e.g., ReadLogs, Restart, OpenShell)
- **Resource**: The Cedar entity representing the Linux resource being accessed (e.g., Service::"cedar-demo", Host::"workshop-vm")
- **Context**: The Cedar context containing point-in-time request information (e.g., local_console, interactive)
- **PARC**: Principal, Action, Resource, Context - the four elements of a Cedar authorization request
- **Unsigned_Authorization**: Cedarling authorization mode where the application constructs and supplies the principal without JWT validation
- **Policy_Server**: The local HTTP server that serves the .cjar file to Tarp with CORS enabled
- **Fixed_Argv**: The immutable array of command and arguments specified in the operations manifest

## Requirements

### Requirement 1: Workshop Virtual Machine Provisioning

**User Story:** As a workshop attendee, I want a pre-configured VM with all dependencies installed, so that I can start the workshop without spending time on installation or configuration.

#### Acceptance Criteria

1. THE Workshop_VM SHALL be a downloadable Ubuntu or Debian image with Tarp, Cedarling Python bindings, and Demo_Service pre-installed
2. THE Workshop_VM SHALL contain two demonstration user accounts: alice (member of developers group) and bob (member of operators group)
3. THE Workshop_VM SHALL have Demo_Service running as a systemd service that writes timestamps to its journal and can be safely restarted repeatedly
4. THE Workshop_VM SHALL have Workshop_Files directory at ~/cedudo-workshop/ containing policy/, examples/, tools/, and README.md subdirectories
5. THE Workshop_VM SHALL have Cedudo installed at /opt/cedudo/ with cedudo.py, operations.json, cedudo.cjar, and venv/
6. THE Workshop_VM SHALL have a symlink at /usr/local/sbin/cedudo pointing to /opt/cedudo/cedudo.py
7. THE Workshop_VM SHALL have a sudoers configuration at /etc/sudoers.d/cedudo permitting only the cedudo helper (not underlying administrative commands)
8. THE Workshop_VM SHALL include a reset script at /opt/cedudo/reset-workshop that restores the workshop to its initial state

### Requirement 2: Operations Manifest and Command Binding

**User Story:** As a security-conscious system designer, I want privileged operations to be bound to fixed command arrays in a root-owned manifest, so that users cannot inject arbitrary commands or arguments.

#### Acceptance Criteria

1. THE Operations_Manifest SHALL be a JSON file at /opt/cedudo/operations.json owned by root with permissions 0644
2. THE Operations_Manifest SHALL define operation entries containing action, resource_type, resource_id, resource_attributes, and argv fields
3. THE Operations_Manifest SHALL include "view-logs" operation mapping to journalctl with fixed service name and line count
4. THE Operations_Manifest SHALL include "status-demo" operation mapping to systemctl status with fixed service name
5. THE Operations_Manifest SHALL include "restart-demo" operation mapping to systemctl restart with fixed service name
6. THE Operations_Manifest SHALL NOT include "root-shell" operation (deliberately excluded for security demonstration)
7. WHEN Cedudo receives an Operation_ID, THE Cedudo SHALL validate that the argv array contains only the executable path and fixed arguments with no user-supplied values
8. WHEN Cedudo validates an executable path, THE Cedudo SHALL verify it is an absolute path, owned by root, not group/world writable, and has execute permission

### Requirement 3: Identity and Principal Construction

**User Story:** As a security engineer, I want the principal identity to be derived from trusted OS sources, so that users cannot impersonate other principals or forge group memberships.

#### Acceptance Criteria

1. WHEN Cedudo is invoked, THE Cedudo SHALL verify it is running with effective UID 0 (root)
2. WHEN Cedudo is invoked, THE Cedudo SHALL extract the original username from SUDO_USER environment variable
3. WHEN Cedudo is invoked, THE Cedudo SHALL extract the original UID from SUDO_UID environment variable
4. WHEN Cedudo is invoked, THE Cedudo SHALL extract the original GID from SUDO_GID environment variable
5. WHEN Cedudo extracts identity, THE Cedudo SHALL validate the username, UID, and GID against the system user database (pwd.getpwnam)
6. IF the original user is root or UID is 0, THEN THE Cedudo SHALL terminate with error "direct root invocation is not a workshop principal"
7. WHEN Cedudo constructs the Principal, THE Cedudo SHALL query group memberships using os.getgrouplist with the username and GID
8. THE Principal SHALL be a Cedar entity of type Linux::User containing uid, gid, groups, home, shell, and cedar_entity_mapping fields
9. THE Cedudo SHALL NOT accept username, UID, GID, or group memberships from command-line arguments

### Requirement 4: Context Derivation from Trusted Environment

**User Story:** As a policy author, I want context information to reflect the actual execution environment, so that I can write policies conditioned on local vs remote access.

#### Acceptance Criteria

1. WHEN Cedudo builds context, THE Cedudo SHALL set local_console to false if SSH_CONNECTION environment variable is present
2. WHEN Cedudo builds context, THE Cedudo SHALL set local_console to false if SSH_CLIENT environment variable is present
3. WHEN Cedudo builds context, THE Cedudo SHALL set local_console to false if "sshd" is found in the process ancestor names
4. WHEN Cedudo builds context, THE Cedudo SHALL set local_console to true if none of the SSH indicators are present
5. WHEN Cedudo builds context, THE Cedudo SHALL set interactive to true if stdin and stdout are both TTYs
6. THE Context SHALL include current_time as Unix timestamp, hostname, local_console, and interactive fields
7. THE Cedudo SHALL NOT accept context values from command-line arguments or user-controlled environment variables

### Requirement 5: Cedarling Initialization and Policy Loading

**User Story:** As a workshop facilitator, I want Cedarling to load only the trusted root-owned policy store, so that users cannot substitute malicious policies.

#### Acceptance Criteria

1. WHEN Cedudo initializes Cedarling, THE Cedudo SHALL validate that /opt/cedudo/cedudo.cjar is a regular file owned by root
2. WHEN Cedudo initializes Cedarling, THE Cedudo SHALL validate that cedudo.cjar is not group/world writable
3. WHEN Cedudo initializes Cedarling, THE Cedudo SHALL remove all CEDARLING_* environment variables inherited from sudo
4. WHEN Cedudo initializes Cedarling, THE Cedudo SHALL set CEDARLING_POLICY_STORE_LOCAL_FN to /opt/cedudo/cedudo.cjar
5. WHEN Cedudo initializes Cedarling, THE Cedudo SHALL set CEDARLING_APPLICATION_NAME to "cedudo"
6. WHEN Cedudo initializes Cedarling, THE Cedudo SHALL create BootstrapConfig from environment and instantiate Cedarling
7. IF Cedarling initialization fails, THEN THE Cedudo SHALL terminate with error "Cedarling initialization failed"

### Requirement 6: Authorization Evaluation

**User Story:** As a system administrator, I want Cedudo to evaluate Cedar policies using unsigned authorization, so that the workshop can teach policy concepts without requiring OIDC infrastructure.

#### Acceptance Criteria

1. WHEN Cedudo evaluates authorization, THE Cedudo SHALL construct a RequestUnsigned containing principal, action, resource, and context
2. WHEN Cedudo evaluates authorization, THE Cedudo SHALL invoke cedarling.authorize_unsigned with the request
3. WHEN Cedudo evaluates authorization, THE Cedudo SHALL extract the decision using result.is_allowed()
4. IF authorization evaluation raises an exception, THEN THE Cedudo SHALL terminate with error "authorization evaluation failed"
5. WHEN authorization is denied, THE Cedudo SHALL log "DENY" with user, uid, operation, action, resource, and local_console to syslog and stderr
6. WHEN authorization is denied, THE Cedudo SHALL terminate with exit code 77 (EX_NOPERM) without executing the privileged command
7. WHEN authorization is permitted, THE Cedudo SHALL log "PERMIT" with user, uid, operation, action, resource, local_console, and exec argv to syslog and stderr

### Requirement 7: Privileged Command Execution

**User Story:** As a security engineer, I want Cedudo to execute only the exact command array from the manifest, so that authorization decisions cannot be subverted by command substitution or argument injection.

#### Acceptance Criteria

1. WHEN Cedudo executes a permitted operation, THE Cedudo SHALL use os.execve with the Fixed_Argv from the operations manifest
2. WHEN Cedudo executes a permitted operation, THE Cedudo SHALL change the working directory to / before execution
3. WHEN Cedudo executes a permitted operation, THE Cedudo SHALL replace the process environment with a minimal safe environment (PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, PAGER, SYSTEMD_PAGER)
4. THE Cedudo SHALL NOT use subprocess.run, subprocess.call, or os.system with shell=True
5. THE Cedudo SHALL NOT concatenate user-supplied strings into shell commands
6. THE Cedudo SHALL NOT accept command names, executable paths, or arguments from command-line parameters beyond the Operation_ID

### Requirement 8: Starting Cedar Policies

**User Story:** As a workshop attendee, I want the VM to include working starter policies, so that I can immediately test authorization decisions without writing policies from scratch.

#### Acceptance Criteria

1. THE Policy_Store SHALL include a permit policy allowing principals in "developers" or "operators" groups to perform Linux::Action::"ReadLogs" on Linux::Service::"cedar-demo"
2. THE Policy_Store SHALL include a permit policy allowing principals in "operators" group to perform Linux::Action::"Restart" on Linux::Service::"cedar-demo" when context.local_console is true
3. THE Policy_Store SHALL include a forbid policy denying all principals from performing Linux::Action::"OpenShell" on any resource
4. THE Policy_Store SHALL include a Cedar schema defining Linux::User, Linux::Service, Linux::Host, Linux::Action entity types
5. THE Policy_Store SHALL be compiled into cedudo.cjar format at ~/cedudo-workshop/policy/cedudo.cjar
6. THE Policy_Store SHALL be deployed to /opt/cedudo/cedudo.cjar with root ownership and 0644 permissions

### Requirement 9: Tarp Policy Testing Environment

**User Story:** As a workshop attendee, I want to test Cedar policies in Tarp before deploying them to the VM, so that I can iterate quickly without affecting the enforcement system.

#### Acceptance Criteria

1. THE Policy_Server SHALL serve cedudo.cjar from ~/cedudo-workshop/policy/ on http://127.0.0.1:8000/ with CORS headers enabled
2. THE Policy_Server SHALL be implemented as a simple Python HTTP server in ~/cedudo-workshop/tools/serve-policy.py
3. THE Workshop_Files SHALL include example unsigned authorization request JSON files in ~/cedudo-workshop/examples/ for alice-read-logs, alice-restart, and bob-restart scenarios
4. WHEN Tarp is configured with the Policy_Server URL, THE Tarp SHALL load cedudo.cjar and enable unsigned authorization testing
5. WHEN an attendee modifies policies, THE attendee SHALL rebuild cedudo.cjar using ~/cedudo-workshop/tools/build-cjar.sh
6. WHEN an attendee rebuilds cedudo.cjar, THE Policy_Server SHALL serve the updated policy store to Tarp without restart

### Requirement 10: Policy Deployment and Verification

**User Story:** As a workshop attendee, I want to deploy tested policies from Tarp to the VM enforcement system, so that I can observe the same authorization decisions controlling real privileged operations.

#### Acceptance Criteria

1. THE Workshop_Files SHALL include a deployment script at ~/cedudo-workshop/tools/deploy-policy.sh
2. WHEN deploy-policy.sh is invoked, THE script SHALL validate cedudo.cjar format
3. WHEN deploy-policy.sh is invoked, THE script SHALL copy ~/cedudo-workshop/policy/cedudo.cjar to /opt/cedudo/cedudo.cjar with sudo
4. WHEN deploy-policy.sh is invoked, THE script SHALL set root ownership and 0644 permissions on /opt/cedudo/cedudo.cjar
5. WHEN alice runs "sudo cedudo view-logs", THE Cedudo SHALL permit the operation (alice is in developers group)
6. WHEN alice runs "sudo cedudo restart-demo" with starter policies, THE Cedudo SHALL deny the operation (alice is not in operators group)
7. WHEN bob runs "sudo cedudo restart-demo" locally with starter policies, THE Cedudo SHALL permit the operation (bob is in operators group and local_console is true)
8. WHEN bob runs "sudo cedudo restart-demo" over SSH with starter policies, THE Cedudo SHALL deny the operation (local_console is false)

### Requirement 11: Workshop Attack Scenarios

**User Story:** As a workshop facilitator, I want attendees to attempt bypass attacks that all fail, so that they understand the security properties of the separation between policy decision and enforcement.

#### Acceptance Criteria

1. WHEN an attendee runs "sudo cedudo ../../bin/bash", THE Cedudo SHALL reject the operation with "unknown operation" error before Cedar evaluation
2. WHEN an attendee runs "sudo cedudo 'restart-demo; /bin/bash'", THE Cedudo SHALL reject the operation with "operation must match [a-z][a-z0-9-]{0,63}" error
3. WHEN an attendee runs "sudo cedudo restart-demo --service ssh", THE Cedudo SHALL accept only "restart-demo" as the Operation_ID and ignore additional arguments
4. WHEN an attendee runs "sudo cedudo root-shell", THE Cedudo SHALL reject the operation with "unknown operation" error (root-shell is not in operations manifest)
5. WHEN an attendee attempts to modify operations.json without sudo, THE file system SHALL deny write access
6. WHEN an attendee attempts to modify cedudo.cjar without sudo, THE file system SHALL deny write access
7. WHEN an attendee attempts to run "sudo systemctl restart cedar-demo" directly, THE sudoers configuration SHALL deny access

### Requirement 12: Policy Modification Exercise

**User Story:** As a workshop attendee, I want to modify Cedar policies to permit developers to restart noncritical services locally, so that I learn how to author and test Cedar conditions.

#### Acceptance Criteria

1. THE Workshop_Files SHALL include editable Cedar policy source at ~/cedudo-workshop/policy/cedar-policy.cedar
2. THE Workshop_Files SHALL include Cedar schema source at ~/cedudo-workshop/policy/cedar-schema.json
3. WHEN an attendee adds a permit policy for principals in "developers" group to perform Restart when resource.critical is false and context.local_console is true, THE policy SHALL be syntactically valid Cedar
4. WHEN an attendee rebuilds cedudo.cjar with the modified policy, THE build-cjar.sh script SHALL compile the policy without errors
5. WHEN an attendee tests the modified policy in Tarp, THE Tarp SHALL show permit decision for alice performing Restart on cedar-demo locally
6. WHEN an attendee deploys the modified policy to /opt/cedudo/, THE Cedudo SHALL permit alice to run "sudo cedudo restart-demo" locally
7. WHEN alice runs "sudo cedudo restart-demo" with the modified policy, THE Demo_Service SHALL restart successfully

### Requirement 13: Contextual Control Exercise

**User Story:** As a workshop attendee, I want to add one contextual control to policies, so that I learn how to use Cedar context to enforce conditional authorization.

#### Acceptance Criteria

1. WHEN an attendee adds a forbid policy denying Restart when context.local_console is false, THE policy SHALL override any matching permit policies
2. WHEN an attendee adds a permit policy requiring principals to be members of both "operators" and "oncall" groups, THE policy SHALL use Cedar set operations on principal.groups
3. WHEN an attendee adds a permit policy conditioned on context.change_ticket being present, THE policy SHALL reference context attributes not initially provided
4. THE Workshop_Files README SHALL provide examples of contextual controls including remote access denial, critical service protection, and multi-group requirements
5. WHEN an attendee deploys a policy with contextual controls, THE Cedudo SHALL evaluate the context conditions during authorization

### Requirement 14: Workshop Timing and Flow

**User Story:** As a workshop facilitator, I want the workshop to fit within 80 minutes with clear phases, so that attendees complete all objectives within the session time.

#### Acceptance Criteria

1. THE workshop SHALL allocate 0-8 minutes for introduction to sudoers complexity and workshop architecture
2. THE workshop SHALL allocate 8-18 minutes for VM inspection and testing initial permissions with alice and bob
3. THE workshop SHALL allocate 18-32 minutes for reproducing Cedar decisions in Tarp with unsigned authorization
4. THE workshop SHALL allocate 32-45 minutes for modifying policies to permit developers to restart noncritical services locally
5. THE workshop SHALL allocate 45-58 minutes for deploying modified policies to the VM and verifying they work
6. THE workshop SHALL allocate 58-70 minutes for attacking the design with bypass attempts that all fail
7. THE workshop SHALL allocate 70-77 minutes for adding one contextual control
8. THE workshop SHALL allocate 77-80 minutes for debrief on separation of concerns (policy decision, enforcement, privilege escalation)

### Requirement 15: Educational Scope Boundaries

**User Story:** As a workshop facilitator, I want the workshop to be explicitly scoped as educational, so that attendees understand this is not production-ready and what would be required for production use.

#### Acceptance Criteria

1. THE workshop materials SHALL state "This is educational, not a production sudo replacement"
2. THE workshop materials SHALL list out-of-scope items including JWT/OIDC integration, policy signing, policy versioning, rollback protection, and Janssen Server installation
3. THE workshop materials SHALL explain that production implementation would require a compiled root-owned enforcement binary
4. THE workshop materials SHALL explain that production implementation would require signed and versioned policy stores
5. THE workshop materials SHALL explain that production implementation would require policy rollback protection and secure decision logging
6. THE workshop materials SHALL explain that production implementation would require stronger session authentication and environment sanitization
7. THE workshop materials SHALL explain that production implementation would require formal review of every operation-to-argv binding
8. THE workshop materials SHALL explain that unsigned authorization is suitable only for local testing without external identity providers

### Requirement 16: Logging and Auditability

**User Story:** As a system administrator, I want all authorization decisions logged with sufficient detail, so that I can audit privileged operations and investigate security events.

#### Acceptance Criteria

1. WHEN Cedudo logs an authorization decision, THE Cedudo SHALL include user, uid, operation, action, resource type, resource id, and local_console in the audit message
2. WHEN Cedudo logs a permit decision, THE Cedudo SHALL include the full exec argv array in the audit message
3. WHEN Cedudo logs to syslog, THE Cedudo SHALL use SysLogHandler with address /dev/log
4. WHEN Cedudo logs to stderr, THE Cedudo SHALL use StreamHandler with format "cedudo[PID]: LEVEL message"
5. WHEN Cedudo encounters a configuration error, THE Cedudo SHALL log the error and terminate without executing the privileged command
6. WHEN Cedudo encounters an authorization evaluation error, THE Cedudo SHALL log the error and terminate without executing the privileged command

### Requirement 17: File and Permission Security

**User Story:** As a security engineer, I want all critical files to be root-owned and protected from modification, so that users cannot tamper with policies, manifests, or enforcement code.

#### Acceptance Criteria

1. WHEN Cedudo validates a trusted file, THE Cedudo SHALL verify the file is a regular file (not a symlink)
2. WHEN Cedudo validates a trusted file, THE Cedudo SHALL verify the file is owned by UID 0 (root)
3. WHEN Cedudo validates a trusted file, THE Cedudo SHALL verify the file is not group writable (S_IWGRP bit is clear)
4. WHEN Cedudo validates a trusted file, THE Cedudo SHALL verify the file is not world writable (S_IWOTH bit is clear)
5. IF a trusted file validation fails, THEN THE Cedudo SHALL terminate with error describing the validation failure
6. THE Operations_Manifest SHALL have ownership root:root and permissions 0644
7. THE Policy_Store SHALL have ownership root:root and permissions 0644
8. THE cedudo.py SHALL have ownership root:root and permissions 0755

### Requirement 18: Error Handling and Fail-Closed Behavior

**User Story:** As a security engineer, I want all errors to fail closed without executing privileged commands, so that authorization cannot be bypassed by triggering error conditions.

#### Acceptance Criteria

1. IF Cedudo cannot read the operations manifest, THEN THE Cedudo SHALL terminate with exit code 78 (EX_CONFIG) without executing any command
2. IF Cedudo receives an unknown Operation_ID, THEN THE Cedudo SHALL terminate with exit code 77 (EX_NOPERM) without executing any command
3. IF Cedudo cannot resolve the invoking user from SUDO_USER, THEN THE Cedudo SHALL terminate with error "invalid sudo identity" without executing any command
4. IF Cedudo cannot initialize Cedarling, THEN THE Cedudo SHALL terminate with exit code 69 (EX_UNAVAILABLE) without executing any command
5. IF Cedudo cannot evaluate the authorization request, THEN THE Cedudo SHALL terminate with exit code 69 (EX_UNAVAILABLE) without executing any command
6. IF Cedudo validates that an executable is group/world writable, THEN THE Cedudo SHALL terminate with error "executable is group/world writable" without executing any command
7. IF authorization evaluation returns deny, THEN THE Cedudo SHALL terminate with exit code 77 (EX_NOPERM) without executing any command

### Requirement 19: Demo Service Implementation

**User Story:** As a workshop attendee, I want a harmless demo service that is safe to restart repeatedly, so that I can practice privileged operations without risk of damaging the system.

#### Acceptance Criteria

1. THE Demo_Service SHALL be a systemd service named cedar-demo.service
2. THE Demo_Service SHALL write a timestamp to the systemd journal at regular intervals
3. THE Demo_Service SHALL have no external network dependencies
4. THE Demo_Service SHALL contain no important data or state
5. WHEN Demo_Service is restarted, THE Demo_Service SHALL restart without errors
6. WHEN Demo_Service is restarted repeatedly, THE Demo_Service SHALL not degrade system performance
7. THE Demo_Service SHALL run as a non-root user with minimal privileges

### Requirement 20: Workshop Documentation

**User Story:** As a workshop attendee, I want clear documentation of the workshop objectives, architecture, and exercises, so that I can follow along and reference materials after the workshop.

#### Acceptance Criteria

1. THE Workshop_Files SHALL include a README.md at ~/cedudo-workshop/README.md documenting workshop objectives and architecture
2. THE README.md SHALL explain the separation of concerns: sudo (privilege transition), cedudo (enforcement), Cedarling (decision), Tarp (testing)
3. THE README.md SHALL provide step-by-step instructions for each workshop phase
4. THE README.md SHALL include diagrams showing the architecture with Tarp, Policy_Server, cedudo, and Cedarling components
5. THE README.md SHALL document the PARC model: Principal (Linux user), Action (privileged capability), Resource (service/host), Context (session conditions)
6. THE README.md SHALL provide examples of permit, deny, and forbid policies with explanations
7. THE README.md SHALL include a troubleshooting section for common issues (Policy_Server not running, Tarp not loading policies, sudoers misconfiguration)
8. THE README.md SHALL provide instructions for resetting the workshop to its initial state using the reset script
