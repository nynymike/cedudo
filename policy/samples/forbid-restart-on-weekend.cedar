// Block all restarts on weekends. A forbid overrides every permit, so this
// enforces the rule regardless of which policy would otherwise grant access.
@id("forbid-restart-on-weekend")
forbid (
    principal,
    action == Linux::Action::"restart",
    resource
)
when {
    context has is_weekend &&
    context.is_weekend
};
