// Block restarts in the first 10 seconds of a session, a simple guard
// against scripted "log in and immediately act" automation. A value of -1
// means the age is unknown; fail safe by also blocking in that case.
@id("forbid-restart-fresh-session")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when {
    context has session_age_seconds &&
    context.session_age_seconds < 10
};
