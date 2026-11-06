@id("forbid-restart-outside-hours")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when {
    context has hour &&
    (context.hour < 9 || context.hour >= 17)
};
