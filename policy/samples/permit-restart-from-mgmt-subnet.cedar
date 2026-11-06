// Permit operators to restart only from the management subnet 10.0.0.0/24.
// login_source_ip is an ADVISORY signal (sshd-set, forgeable locally), so it
// is paired with group membership rather than used alone.
@id("permit-restart-from-mgmt-subnet")
permit (
    principal is Linux::User,
    action == Linux::Action::"restart",
    resource
)
when {
    principal has groups &&
    principal.groups.contains("operators") &&
    context has login_source_ip &&
    context.login_source_ip like "10.0.0.*"
};
