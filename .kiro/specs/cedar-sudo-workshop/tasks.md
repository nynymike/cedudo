# Implementation Plan: Cedar Sudo Workshop

## Overview

This implementation plan creates a complete 80-minute hands-on workshop teaching Cedar authorization for privileged Linux operations. The workshop demonstrates separation of concerns: sudo (privilege escalation), cedudo (policy enforcement), Cedarling (policy decision), and Tarp (policy testing).

The implementation uses Python 3 with cedarling-python bindings, Cedar policy language, systemd for the demo service, and bash scripts for tooling. All components are designed for educational purposes to teach authorization concepts, not for production deployment.

## Tasks

- [ ] 1. Set up VM base infrastructure and user accounts
  - Create Ubuntu/Debian VM base configuration
  - Create alice user (uid=1000, primary group=developers)
  - Create bob user (uid=1001, primary group=operators)
  - Create developers and operators system groups
  - Configure SSH access for both users
  - _Requirements: 1.2, 3.5_

- [ ] 2. Implement and deploy demo service
  - [ ] 2.1 Create cedar-demo-service.sh timestamp script
    - Write bash script that outputs timestamps to stdout every 30 seconds
    - Make script executable
    - Install to /usr/local/bin/cedar-demo-service.sh
    - Set ownership to root:root with 0755 permissions
    - _Requirements: 19.2, 19.3, 19.4_

  - [ ] 2.2 Create cedar-demo.service systemd unit
    - Write systemd service file with Type=simple
    - Configure to run as user=nobody (unprivileged)
    - Set ExecStart to /usr/local/bin/cedar-demo-service.sh
    - Configure Restart=always with RestartSec=5
    - Install to /etc/systemd/system/cedar-demo.service
    - _Requirements: 19.1, 19.7_

  - [ ] 2.3 Enable and start demo service
    - Reload systemd daemon configuration
    - Enable cedar-demo.service for automatic start
    - Start the service and verify it's running
    - Verify journal output contains timestamps
    - _Requirements: 1.3, 19.5, 19.6_

- [ ] 3. Create Cedar schema and starter policies
  - [ ] 3.1 Create Cedar schema definition
    - Create ~/cedudo-workshop/policy/ directory structure
    - Write cedar-schema.json with Linux::User entity type (uid, gid, groups, home, shell attributes)
    - Add Linux::Service entity type (environment, critical attributes)
    - Add Linux::Host entity type
    - Define Linux namespace actions: ReadLogs, ViewStatus, Restart, OpenShell
    - _Requirements: 8.4, 12.2_

  - [ ] 3.2 Write starter Cedar policies
    - Write permit policy for developers/operators to ReadLogs on cedar-demo service
    - Write permit policy for operators to Restart cedar-demo when local_console is true
    - Write forbid policy denying all OpenShell actions
    - Save policies to ~/cedudo-workshop/policy/cedar-policy.cedar
    - _Requirements: 8.1, 8.2, 8.3, 12.1_

- [ ] 4. Create policy build and deployment tooling
  - [ ] 4.1 Create build-cjar.sh script
    - Write bash script to compile Cedar policies and schema into .cjar format
    - Validate cedar-policy.cedar syntax before building
    - Output to ~/cedudo-workshop/policy/cedudo.cjar
    - Add error handling for compilation failures
    - Make script executable
    - _Requirements: 9.5, 12.4_

  - [ ] 4.2 Create serve-policy.py HTTP server
    - Write Python HTTP server with CORS headers enabled
    - Configure to serve from current directory on 127.0.0.1:8000
    - Add Access-Control-Allow-Origin: * header
    - Handle OPTIONS preflight requests
    - Save to ~/cedudo-workshop/tools/serve-policy.py
    - Make script executable
    - _Requirements: 9.1, 9.2_

  - [ ] 4.3 Create deploy-policy.sh deployment script
    - Write bash script to validate cedudo.cjar file exists
    - Copy ~/cedudo-workshop/policy/cedudo.cjar to /opt/cedudo/cedudo.cjar using sudo
    - Set ownership to root:root
    - Set permissions to 0644
    - Add validation that source file is readable
    - Make script executable
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 5. Create operations manifest
  - Create /opt/cedudo directory with root ownership
  - Write operations.json with view-logs operation (journalctl -u cedar-demo -n 20)
  - Add status-demo operation (systemctl status cedar-demo)
  - Add restart-demo operation (systemctl restart cedar-demo)
  - Set action, resource_type, resource_id, resource_attributes for each operation
  - Explicitly exclude root-shell operation from manifest
  - Set ownership to root:root with 0644 permissions
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 6. Implement cedudo.py enforcement point
  - [ ] 6.1 Create Python virtual environment and install dependencies
    - Create /opt/cedudo/venv Python virtual environment
    - Install cedarling-python package via pip
    - Set ownership to root:root for entire venv directory
    - _Requirements: 1.5_

  - [ ] 6.2 Implement operation validation and manifest loading
    - Write operation ID regex validation ([a-z][a-z0-9-]{0,63})
    - Implement load_operation() to read and validate operations.json
    - Validate operation contains required fields: action, resource_type, resource_id, argv
    - Validate argv[0] is absolute path to root-owned executable
    - Validate executable is not group/world writable
    - _Requirements: 2.7, 2.8, 18.2_

  - [ ] 6.3 Implement principal construction from trusted sources
    - Validate effective UID is 0 (root)
    - Extract SUDO_USER, SUDO_UID, SUDO_GID from environment
    - Validate against system user database using pwd.getpwnam()
    - Reject if original user is root or UID is 0
    - Query group memberships using os.getgrouplist()
    - Construct EntityData with Linux::User type and all attributes
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ] 6.4 Implement context derivation from environment
    - Check for SSH_CONNECTION and SSH_CLIENT environment variables
    - Search process ancestry for "sshd" using /proc filesystem
    - Set local_console to false if any SSH indicators present
    - Set interactive based on isatty() checks for stdin/stdout
    - Add current_time (Unix timestamp) and hostname fields
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ] 6.5 Implement Cedarling initialization with policy store
    - Validate /opt/cedudo/cedudo.cjar is regular file owned by root
    - Validate policy store is not group/world writable
    - Remove all CEDARLING_* environment variables
    - Set CEDARLING_POLICY_STORE_LOCAL_FN to /opt/cedudo/cedudo.cjar
    - Set CEDARLING_APPLICATION_NAME to "cedudo"
    - Create BootstrapConfig and instantiate Cedarling
    - Fail closed on initialization errors
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ] 6.6 Implement authorization evaluation
    - Construct RequestUnsigned with principal, action, resource, context
    - Call cedarling.authorize_unsigned()
    - Extract decision using result.is_allowed()
    - Handle authorization evaluation exceptions with fail-closed behavior
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 6.7 Implement decision enforcement and logging
    - Log DENY decisions with user, uid, operation, action, resource, local_console
    - Exit with code 77 (EX_NOPERM) on deny without executing command
    - Log PERMIT decisions with all audit fields plus exec argv
    - Log to both stderr and syslog (/dev/log)
    - _Requirements: 6.5, 6.6, 6.7, 16.1, 16.2, 16.3, 16.4_

  - [ ] 6.8 Implement secure command execution
    - Use os.execve with fixed argv from manifest (no shell)
    - Change working directory to / before execution
    - Replace environment with minimal safe environment (PATH, HOME, USER, LOGNAME, LANG, TERM, PAGER, SYSTEMD_PAGER)
    - Never use subprocess with shell=True
    - Never concatenate user-supplied strings into commands
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 6.9 Implement file validation and error handling
    - Create require_trusted_file() function for root-owned file validation
    - Validate files are regular files (not symlinks)
    - Validate files are owned by UID 0
    - Validate files are not group/world writable (check S_IWGRP, S_IWOTH bits)
    - Fail closed on all validation errors
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 18.1_

  - [ ]* 6.10 Write unit tests for cedudo.py validation functions
    - Test operation ID regex validation with valid and invalid inputs
    - Test principal construction with mocked SUDO_* environment variables
    - Test context derivation with SSH and non-SSH scenarios
    - Test trusted file validation with various permission scenarios
    - Test fail-closed behavior on various error conditions
    - _Requirements: 18.3, 18.4, 18.5, 18.6, 18.7_

- [ ] 7. Configure sudoers integration
  - Create /etc/sudoers.d/cedudo configuration file
  - Add rule: %developers ALL=(root) /usr/local/sbin/cedudo *
  - Add rule: %operators ALL=(root) /usr/local/sbin/cedudo *
  - Set ownership to root:root with 0440 permissions
  - Validate sudoers syntax with visudo -c
  - Create symlink /usr/local/sbin/cedudo -> /opt/cedudo/cedudo.py
  - Set cedudo.py ownership to root:root with 0755 permissions
  - _Requirements: 1.5, 1.6, 1.7_

- [ ] 8. Checkpoint - Verify core enforcement system
  - Test alice can run: sudo cedudo view-logs (should PERMIT)
  - Test alice running: sudo cedudo restart-demo (should DENY)
  - Test bob can run: sudo cedudo restart-demo locally (should PERMIT)
  - Test alice cannot run: sudo systemctl restart cedar-demo (should be blocked by sudoers)
  - Verify audit logs appear in syslog with correct format
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Create Tarp testing examples
  - [ ] 9.1 Create alice-read-logs.json example request
    - Write unsigned request JSON with alice principal (uid=1000, groups=["developers"])
    - Set action to Linux::Action::"ReadLogs"
    - Set resource to Linux::Service::"cedar-demo" with critical=false
    - Set context with local_console=true, interactive=true
    - _Requirements: 9.3_

  - [ ] 9.2 Create alice-restart.json example request
    - Write unsigned request JSON with alice principal
    - Set action to Linux::Action::"Restart"
    - Set resource to Linux::Service::"cedar-demo"
    - Set context with local_console=true
    - _Requirements: 9.3_

  - [ ] 9.3 Create bob-restart.json example request
    - Write unsigned request JSON with bob principal (uid=1001, groups=["operators"])
    - Set action to Linux::Action::"Restart"
    - Set resource to Linux::Service::"cedar-demo"
    - Set context with local_console=true
    - _Requirements: 9.3_

  - [ ] 9.4 Create bob-restart-remote.json example request
    - Write unsigned request JSON with bob principal
    - Set action to Linux::Action::"Restart"
    - Set resource to Linux::Service::"cedar-demo"
    - Set context with local_console=false (SSH scenario)
    - _Requirements: 10.8_

  - [ ] 9.5 Create root-shell.json example request
    - Write unsigned request with alice or bob principal
    - Set action to Linux::Action::"OpenShell"
    - Set resource to Linux::Host::"workshop-vm"
    - Set context with local_console=true
    - _Requirements: 8.3_

- [ ] 10. Build initial policy store
  - Run build-cjar.sh to compile starter policies
  - Verify cedudo.cjar created in ~/cedudo-workshop/policy/
  - Deploy initial policy to /opt/cedudo/cedudo.cjar using deploy-policy.sh
  - Verify /opt/cedudo/cedudo.cjar has root:root ownership and 0644 permissions
  - _Requirements: 8.5, 8.6, 10.3, 10.4_

- [ ] 11. Create workshop documentation
  - [ ] 11.1 Write README.md introduction and architecture
    - Document workshop objectives and 80-minute timing
    - Explain separation of concerns: sudo, cedudo, Cedarling, Tarp
    - Create architecture diagram showing component relationships
    - Explain PARC model: Principal, Action, Resource, Context
    - _Requirements: 20.1, 20.2, 20.5_

  - [ ] 11.2 Document VM inspection phase instructions
    - Provide commands for checking user identity and groups
    - Document how to check cedar-demo.service status
    - Explain how to test initial permissions with alice and bob
    - Document expected PERMIT and DENY outcomes
    - _Requirements: 20.3, 14.2_

  - [ ] 11.3 Document Tarp testing workflow
    - Explain how to start serve-policy.py server
    - Document Tarp configuration with http://127.0.0.1:8000/cedudo.cjar URL
    - Provide instructions for loading example request JSON files
    - Explain how to observe permit/deny decisions in Tarp
    - Document policy modification and rebuild workflow
    - _Requirements: 20.3, 14.3, 14.4_

  - [ ] 11.4 Document policy modification exercise
    - Provide example of adding permit policy for developers to restart noncritical services locally
    - Show complete Cedar policy syntax with when conditions
    - Document build-cjar.sh usage
    - Document deploy-policy.sh usage
    - Provide verification steps after deployment
    - _Requirements: 20.3, 14.4, 14.5, 12.3, 12.6, 12.7_

  - [ ] 11.5 Document attack scenario exercises
    - List all bypass attempts that should fail
    - Explain why each attack fails (operation validation, fixed argv, root-owned files)
    - Document expected error messages
    - _Requirements: 20.3, 14.6, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ] 11.6 Document contextual control exercises
    - Provide examples of forbid policies for remote access denial
    - Show permit policies requiring multiple group memberships
    - Demonstrate policies conditioned on resource attributes
    - Document how to add and test context-based policies
    - _Requirements: 20.3, 14.7, 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ] 11.7 Write educational scope disclaimer and production requirements
    - State "This is educational, not a production sudo replacement"
    - List out-of-scope items: JWT/OIDC, policy signing, versioning, rollback protection
    - Explain production requirements: compiled binary, signed policies, JWT authentication
    - Document formal review needs for operation-to-argv bindings
    - Explain unsigned authorization scope limitations
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 20.6_

  - [ ] 11.8 Create troubleshooting section
    - Document common issues: Policy server not running
    - Document Tarp not loading policies (CORS, URL configuration)
    - Document sudoers misconfiguration symptoms
    - Document Cedarling initialization failures
    - Provide diagnostic commands for each issue
    - _Requirements: 20.7_

- [ ] 12. Create reset script for workshop state restoration
  - Write /opt/cedudo/reset-workshop bash script
  - Reset policy store to starter policies (copy from backup)
  - Restart cedar-demo.service
  - Clear any test modifications in ~/cedudo-workshop/policy/
  - Restore original operations.json if modified
  - Make script executable with root ownership
  - _Requirements: 1.8, 20.8_

- [ ] 13. Create VM provisioning and packaging scripts
  - [ ] 13.1 Write install-dependencies.sh script
    - Install Python 3 and pip
    - Install systemd development tools
    - Install Cedar CLI tools if available
    - Install required Python packages globally
    - _Requirements: 1.1_

  - [ ] 13.2 Write full-setup.sh provisioning script
    - Execute all setup steps in correct order
    - Create users and groups
    - Install demo service
    - Create directory structures
    - Install cedudo enforcement system
    - Configure sudoers
    - Build and deploy initial policies
    - Set all file permissions correctly
    - _Requirements: 1.1, 1.4, 1.5, 1.6_

  - [ ] 13.3 Create VM export and distribution instructions
    - Document VM sizing requirements (disk, RAM, CPU)
    - Provide export commands for VirtualBox/VMware
    - Document compression and distribution format
    - Create checksum file for download verification
    - _Requirements: 1.1_

- [ ] 14. Integration testing and verification
  - [ ]* 14.1 Test alice permissions with starter policies
    - Verify alice can view logs (PERMIT)
    - Verify alice cannot restart service (DENY)
    - Verify alice cannot run sudo systemctl directly (sudoers blocks)
    - Verify alice cannot run root-shell operation (unknown operation error)
    - _Requirements: 10.5, 10.6_

  - [ ]* 14.2 Test bob permissions with starter policies
    - Verify bob can view logs locally (PERMIT)
    - Verify bob can restart service locally (PERMIT)
    - Verify bob cannot restart service over SSH (DENY due to local_console=false)
    - Verify service actually restarts successfully
    - _Requirements: 10.7, 10.8_

  - [ ]* 14.3 Test Tarp policy testing workflow
    - Start serve-policy.py server
    - Configure Tarp with policy URL
    - Load alice-read-logs.json and verify PERMIT
    - Load alice-restart.json and verify DENY
    - Load bob-restart.json and verify PERMIT
    - Load bob-restart-remote.json and verify DENY
    - Load root-shell.json and verify DENY (forbid policy)
    - _Requirements: 9.4_

  - [ ]* 14.4 Test policy modification and deployment workflow
    - Modify cedar-policy.cedar to add developers restart permission for noncritical services locally
    - Run build-cjar.sh successfully
    - Test modified policy in Tarp (alice restart should now PERMIT)
    - Deploy with deploy-policy.sh
    - Test alice can now run sudo cedudo restart-demo successfully
    - Verify service restarts
    - _Requirements: 10.5, 10.6, 12.5, 12.6, 12.7_

  - [ ]* 14.5 Test all attack scenarios fail as expected
    - Test: sudo cedudo ../../bin/bash (should reject with "unknown operation")
    - Test: sudo cedudo 'restart-demo; /bin/bash' (should reject with regex validation error)
    - Test: sudo cedudo restart-demo --service ssh (should ignore extra arguments, use only "restart-demo")
    - Test: sudo cedudo root-shell (should reject with "unknown operation")
    - Test: attempt to modify operations.json without sudo (should fail permission denied)
    - Test: attempt to modify cedudo.cjar without sudo (should fail permission denied)
    - Test: sudo systemctl restart cedar-demo (should fail sudoers blocks)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ]* 14.6 Test logging and auditability
    - Verify PERMIT decisions logged to syslog with all required fields
    - Verify DENY decisions logged to syslog with all required fields
    - Verify logs include user, uid, operation, action, resource, local_console
    - Verify PERMIT logs include full exec argv array
    - Verify logs appear on stderr for user visibility
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

  - [ ]* 14.7 Test error handling and fail-closed behavior
    - Test behavior when operations.json is missing (should fail with EX_CONFIG)
    - Test behavior with invalid SUDO_USER (should fail with "invalid sudo identity")
    - Test behavior when policy store is missing (should fail with Cedarling initialization error)
    - Test behavior when policy store is world-writable (should fail with permission validation error)
    - Verify no commands execute in any error condition
    - _Requirements: 18.1, 18.3, 18.4, 18.5, 18.6, 18.7_

- [ ] 15. Final checkpoint - Complete system validation
  - Verify all workshop files in place with correct ownership and permissions
  - Test complete workshop flow from VM inspection through policy modification
  - Verify reset script restores workshop to initial state
  - Test all documentation instructions work correctly
  - Verify 80-minute timing is achievable
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster implementation
- Each task references specific requirements for traceability
- The implementation uses Python 3 for all scripts and enforcement logic
- Cedar policies are written in Cedar policy language (.cedar format)
- All root-owned files must be validated for ownership and permissions before use
- The workshop is explicitly educational and not production-ready
- Checkpoints ensure incremental validation at major milestones
- Integration tests validate end-to-end workshop scenarios

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": ["1.1", "2.1", "3.1", "13.1"]
    },
    {
      "id": 1,
      "tasks": ["2.2", "3.2", "5.1", "6.1"]
    },
    {
      "id": 2,
      "tasks": ["2.3", "4.1", "4.2", "6.2"]
    },
    {
      "id": 3,
      "tasks": ["4.3", "6.3", "6.4", "9.1", "9.2", "9.3"]
    },
    {
      "id": 4,
      "tasks": ["6.5", "6.9", "9.4", "9.5"]
    },
    {
      "id": 5,
      "tasks": ["6.6", "7.1"]
    },
    {
      "id": 6,
      "tasks": ["6.7", "6.8", "10.1"]
    },
    {
      "id": 7,
      "tasks": ["6.10", "11.1", "11.2", "11.3"]
    },
    {
      "id": 8,
      "tasks": ["11.4", "11.5", "11.6", "12.1"]
    },
    {
      "id": 9,
      "tasks": ["11.7", "11.8", "13.2"]
    },
    {
      "id": 10,
      "tasks": ["13.3", "14.1", "14.2", "14.3"]
    },
    {
      "id": 11,
      "tasks": ["14.4", "14.5", "14.6", "14.7"]
    }
  ]
}
```
