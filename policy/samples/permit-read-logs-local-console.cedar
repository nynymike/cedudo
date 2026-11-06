// Permit reading logs only from an interactive local console on a pseudo
// terminal. Demonstrates local_console, interactive, and tty together.
@id("permit-read-logs-local-console")
permit (
    principal is Linux::User,
    action == Linux::Action::"read-logs",
    resource
)
when {
    context.local_console &&
    context.interactive &&
    context has tty &&
    context.tty like "pts/*"
};
